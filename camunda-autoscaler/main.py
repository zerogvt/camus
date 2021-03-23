import os
import threading
import atexit
import requests
import sys
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from pprint import pprint
from flask import Flask, request, jsonify
from elasticapm.contrib.flask import ElasticAPM

VERSION = '0.0.1'
CHECK_PERIOD = 3
CAMUNDA_SERVICE_HOST = os.getenv('CAMUNDA_SERVICE_SERVICE_HOST')
CAMUNDA_SERVICE_PORT = os.getenv('CAMUNDA_SERVICE_SERVICE_PORT')
CHECK_URL = (f"http://{CAMUNDA_SERVICE_HOST}:{CAMUNDA_SERVICE_PORT}"
             "/engine-rest/history/process-instance/count")
# CHECK_URL = "http://127.0.0.1:51343/engine-rest/history/process-instance/count"
checker = threading.Thread()
new_proc = 0
old_proc = 0
first_time = True


def autoscaler():
    app = Flask(__name__)
    config.load_incluster_config()
    # config.load_kube_config()
    k1 = client.CoreV1Api()
    k2 = client.AppsV1Api()

    def interrupt():
        global checker
        checker.cancel()

    def get_pods(name='camunda-deployment-'):
        ret = k1.list_pod_for_all_namespaces(watch=False)
        count = 0
        for i in ret.items:
            if i.metadata.name.startswith(name):
                count += 1
        return count

    def scale_deployment():
        try:
            dep = k2.read_namespaced_deployment("camunda-deployment",
                                                "default",
                                                pretty="true")
            # pprint(dep)
            k2.patch_namespaced_deployment("camunda-deployment",
                                           "default",
                                           {"spec": {"replicas": 2}})
        except ApiException as e:
            print(e)

    def check():
        global checker, new_proc, old_proc, first_time
        try:
            r = requests.get(CHECK_URL)
            r.raise_for_status()
            new_proc = r.json()['count']
            if first_time:
                diff_proc = 0
                first_time = False
            else:
                # AUTOSCALER LOGIC
                diff_proc = new_proc - old_proc
                n_replicas = get_pods()
                proc_per_inst = diff_proc/n_replicas
                print(new_proc, old_proc, diff_proc, n_replicas, proc_per_inst)
                scale_deployment()
                if proc_per_inst >= 20 and n_replicas < 4:
                    print("UP")
                elif proc_per_inst <= 10 and n_replicas > 1:
                    scale_deployment()
                    print("DOWN")
            old_proc = new_proc
        except (requests.exceptions.RequestException,
                ConnectionError,
                KeyError) as e:
            print(e)
        sys.stdout.flush()
        checker = threading.Timer(CHECK_PERIOD, check, ())
        checker.start()

    check()
    # When you kill Flask (SIGTERM), clear the trigger for the next thread
    atexit.register(interrupt)
    return app


# create flask app
app = autoscaler()

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
    print(f"[INFO] Camunda service url: {CHECK_URL}")
    port = 5050
    if 'AUTOSCALER_PORT' in os.environ:
        port = os.environ['AUTOSCALER_PORT']
    # allow multiple threads (i.e. multiple concurrent users)
    app.run(threaded=True, port=port)
