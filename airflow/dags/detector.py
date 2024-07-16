import pathlib
import typing

import pendulum
import requests

from airflow.decorators import dag, task


def fetch_last_file(directory: pathlib.Path) -> pathlib.Path:
    files = list()
    for file in directory.iterdir():
        if file.is_file() and str(file).endswith("csv"):
            files.append(file)

    if not files:
        raise Exception(f"empty directory: {directory}")

    return max(files)


@dag(
    schedule=None,
    start_date=pendulum.datetime(2024, 4, 1, tz="UTC"),
    catchup=False,
    tags=["monitoring"],
)
def drift_detector():
    @task()
    def fetch_features_control() -> str:
        last_file = fetch_last_file(pathlib.Path("/opt/data/control"))
        return str(last_file.absolute())

    @task()
    def fetch_features_current() -> str:
        last_file = fetch_last_file(pathlib.Path("/opt/data/audit"))
        return str(last_file.absolute())

    @task()
    def fetch_metadata() -> typing.Dict[str, str]:
        return {
            "dteday": "datetime",
            "temp": "numeric",
            "atemp": "numeric",
            "hum": "numeric",
            "windspeed": "numeric",
            "casual": "numeric",
            "registered": "numeric",
            "cnt": "numeric",
            "weathersit": "numeric",
        }

    @task.virtualenv(
        use_dill=True,
        system_site_packages=False,
        requirements=["pandas==2.2.2", "scipy==1.12.0"],
    )
    def apply_detection(control_path: str, current_path: str, metadata: dict):
        import pandas as pd
        from scipy.stats import ks_2samp

        def ks_test(old_feature, new_feature):
            ks_statistic, p_value = ks_2samp(old_feature, new_feature)
            return p_value

        control_dataset = pd.read_csv(control_path)
        current_dataset = pd.read_csv(current_path)

        feature_columns = [k for k, v in metadata.items() if v == "numeric"]

        result = {}
        for column in feature_columns:
            p_value = ks_test(control_dataset[column], current_dataset[column])
            result[column] = p_value

        return result

    @task()
    def send_metrics(metrics: typing.Dict[str, float]):
        for feature, value in metrics.items():
            feature = feature
            metric = "p_value"

            reply = requests.post(
                "http://monitor:5445/drift",
                params={"feature": feature, "metric": metric, "value": value},
            )

            if reply.text != "ok":
                raise Exception(reply.text)

    control = fetch_features_control()
    current = fetch_features_current()
    metadata = fetch_metadata()

    metrics = apply_detection(control, current, metadata)

    send_metrics(metrics)


drift_detector()
