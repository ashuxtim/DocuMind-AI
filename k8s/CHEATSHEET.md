# Kubernetes Command Cheat Sheet

## Cluster
```bash
kubectl cluster-info              # Cluster endpoint
kubectl get nodes                 # List nodes
minikube status                   # Minikube health
minikube dashboard                # Web UI
```

## Pods
```bash
kubectl get pods                  # List all pods
kubectl get pods -o wide          # With node + IP
kubectl get pods -l app=fastapi   # Filter by label
kubectl describe pod <name>       # Full details + events
kubectl logs <name>               # Container logs
kubectl logs <name> --previous    # Logs from crashed container
kubectl logs -f <name>            # Follow (tail -f)
kubectl exec -it <name> -- bash   # Shell into pod
kubectl delete pod <name>         # Delete (Deployment recreates it)
```

## Deployments
```bash
kubectl get deployments                              # List
kubectl scale deployment <name> --replicas=3         # Scale
kubectl set image deployment/<name> <c>=<img>        # Update image
kubectl rollout status deployment/<name>             # Watch rollout
kubectl rollout undo deployment/<name>               # Rollback
```

## StatefulSets
```bash
kubectl get statefulsets                             # List
kubectl scale statefulset <name> --replicas=3        # Scale (ordered!)
kubectl delete statefulset <name>                    # Delete (keeps PVCs)
```

## Services
```bash
kubectl get services                                 # List
kubectl get endpoints <name>                         # Backend pod IPs
kubectl port-forward svc/<name> 8000:8000            # Local tunnel
```

## Ingress
```bash
kubectl get ingress                                  # List
kubectl describe ingress <name>                      # Rules + annotations
```

## Config & Secrets
```bash
kubectl get configmaps                               # List ConfigMaps
kubectl describe configmap <name>                    # View contents
kubectl get secrets                                  # List Secrets
kubectl get secret <name> -o jsonpath='{.data}'      # View (base64)
```

## Storage
```bash
kubectl get pvc                                      # List PVCs
kubectl get pv                                       # List PVs
kubectl describe pvc <name>                          # Binding details
```

## Debugging
```bash
kubectl describe pod <name>                          # Events + status
kubectl logs <name> --previous                       # Crashed container
kubectl get events --sort-by='.lastTimestamp'         # Recent events
kubectl top pods                                     # Resource usage
kubectl run debug --image=busybox -it --rm -- sh     # Debug pod
```

## Minikube
```bash
minikube start --cpus=4 --memory=8192               # Start
minikube stop                                        # Pause
minikube delete                                      # Destroy cluster
minikube ip                                          # Node IP
minikube image load <image>                          # Load Docker image
minikube addons enable ingress                       # Enable addon
minikube service <name> --url                        # Get service URL
```