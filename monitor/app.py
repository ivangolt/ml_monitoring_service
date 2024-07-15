import prometheus_client
from flask import Flask, request
from werkzeug.middleware.dispatcher import DispatcherMiddleware

METRICS_REGISTRY = prometheus_client.CollectorRegistry()

DRIFT = "drift"

METRICS = {
    DRIFT: prometheus_client.Gauge(
        DRIFT,
        documentation="explains drift in metrics",
        labelnames=["feature", "metric"],
        registry=METRICS_REGISTRY,
    )
}

app = Flask(__name__)
app.wsgi_app = DispatcherMiddleware(
    app.wsgi_app,
    {"/metrics": prometheus_client.make_wsgi_app(registry=METRICS_REGISTRY)},
)


@app.route(f"/{DRIFT}", methods=["POST"])
def update_model_metric():
    feature = request.args.get("feature", type=str)
    metric = request.args.get("metric", type=str)
    value = request.args.get("value", type=float)

    METRICS[DRIFT].labels(feature=feature, metric=metric).set(value)

    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5445, debug=False)
