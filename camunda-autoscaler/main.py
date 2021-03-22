import os
import threading
import atexit
import requests
from flask import Flask, request, jsonify
from elasticapm.contrib.flask import ElasticAPM

CHECK_PERIOD = 10
CHECK_URL = "http://127.0.0.1:51343/engine-rest/history/process-instance/count"

checker = threading.Thread()
new_count = 0
old_count = 0
first_time = True


def create_app():
    app = Flask(__name__)

    def interrupt():
        global checker
        checker.cancel()

    def check():
        global checker, new_count, old_count, first_time
        try:
            r = requests.get(CHECK_URL)
            r.raise_for_status()
            new_count = r.json()['count']
            diff = new_count - old_count
            if first_time:
                diff = 0
                first_time = False
            print(new_count, old_count, diff, first_time)
            old_count = new_count
        except (requests.exceptions.RequestException,
                ConnectionError,
                KeyError) as e:
            print(e)
        checker = threading.Timer(CHECK_PERIOD, check, ())
        checker.start()

    check()
    # When you kill Flask (SIGTERM), clear the trigger for the next thread
    atexit.register(interrupt)
    return app


# create flask app
app = create_app()

# monitoring instrumentation
app.config['ELASTIC_APM'] = {
  'SERVICE_NAME': 'camunda',
  'SECRET_TOKEN': 'PVFth76ZcIie49mnn5',
  'SERVER_URL': 'https://f04e2eb899c44e1fbc3edd823dbb25f4.apm.westus2.azure.elastic-cloud.com:443',
  'ENVIRONMENT': 'production',
}
apm = ElasticAPM(app)

@app.route('/stats', methods=['GET'])
def fib_view():
    response = {}
    status = 200
    response["MESSAGE"] = "stats"
    return jsonify(response), status

@app.route('/')
def index():
    return ("<html><title>Help</title><body>"
            "Endpoints:<br>"
            "/stats<br>"
            "/alive<br>"
            "</body></html>")


if __name__ == '__main__':
    port = 5050
    if 'AUTOSCALER_PORT' in os.environ:
        port = os.environ['AUTOSCALER_PORT']
    # allow multiple threads (i.e. multiple concurrent users)
    app.run(threaded=True, port=port)
