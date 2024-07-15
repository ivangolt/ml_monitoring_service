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
def simple_detector():
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
        requirements=[
            #'evidently==0.4.19'
            "pandas==2.2.2"
        ],
    )
    def apply_detection(control_path: str, current_path: str, metadata: dict):
        import pandas as pd

        control_dataset = pd.read_csv(control_path)
        current_dataset = pd.read_csv(current_path)

        feature_columns = [k for k, v in metadata.items() if v == "numeric"]

        result = (
            (
                current_dataset[feature_columns].quantile(0.5)
                / control_dataset[feature_columns].quantile(0.5)
                - 1
            )
            * 100
        ).rename(lambda x: x + "__median").to_dict() | (
            (
                current_dataset[feature_columns].mean()
                / control_dataset[feature_columns].mean()
                - 1
            )
            * 100
        ).rename(lambda x: x + "__mean").to_dict()

        return result

    @task()
    def send_metrics(metrics: typing.Dict[str, float]):
        for feature_metric, value in metrics.items():
            split_index = feature_metric.rfind("__")
            feature = feature_metric[:split_index]
            metric = feature_metric[split_index + 2 :]

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


simple_detector()
