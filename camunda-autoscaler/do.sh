docker build -t zerogvt/autoscaler:latest .; docker push zerogvt/autoscaler:latest
kubectl delete -f autoscaler_deployment.yaml ; kubectl create -f autoscaler_deployment.yaml
kubectl get po