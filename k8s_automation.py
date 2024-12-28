import argparse
import subprocess
import os
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import time
import yaml

def run_command(command):
    """Run a shell command and return the output."""
    try:
        result = subprocess.run(command, check=True, shell=True, capture_output=True, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Command '{command}' failed with exit code {e.returncode}")
        print("Error output:")
        print(e.stderr)
        raise

def connect_to_cluster(context):
    """Connect to the Kubernetes cluster using the specified context."""
    try:
        run_command(f"kubectl config use-context {context}")
        print(f"Connected to Kubernetes cluster with context: {context}")
    except Exception as e:
        print(f"Failed to connect to cluster: {e}")

def install_helm():
    """Install Helm if not already installed."""
    try:
        run_command("helm version")
        print("Helm is already installed.")
    except:
        print("Installing Helm...")
        run_command("curl https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3 | bash")
        print("Helm installed successfully.")

def install_keda():
    """Install KEDA using Helm and ensure it is running."""
    try:
        # Add the KEDA Helm repository and update
        run_command("helm repo add kedacore https://kedacore.github.io/charts")
        run_command("helm repo update")

        # Check if KEDA is already installed
        try:
            output = run_command("helm list -n keda | grep keda")
            print("KEDA is already installed. Current status:")
            show_keda_status()
        except subprocess.CalledProcessError:
            # KEDA is not installed, proceed with installation
            output = run_command("helm install keda kedacore/keda --namespace keda --create-namespace")
            print(output)
            print("KEDA installation initiated. Waiting for KEDA pods to be in the Running state...")
            wait_for_keda_pods()

    except Exception as e:
        print(f"Failed to install or check KEDA: {e}")

def show_keda_status():
    """Show the status of KEDA pods."""
    try:
        output = run_command("kubectl get pods -n keda")
        print(output)
    except Exception as e:
        print(f"Failed to get KEDA pod status: {e}")

def wait_for_keda_pods():
    """Wait for KEDA pods to be running."""
    config.load_kube_config()
    v1 = client.CoreV1Api()

    while True:
        pods = v1.list_namespaced_pod(namespace="keda", label_selector="app.kubernetes.io/name=keda")
        all_running = all(pod.status.phase == "Running" for pod in pods.items)
        if all_running:
            print("KEDA is successfully installed and all pods are running.")
            show_keda_status()
            break
        else:
            print("Waiting for KEDA pods to be running...")
            time.sleep(5)  # Wait before checking again

def create_deployment_from_args(args):
    """Create a Kubernetes deployment with KEDA scaling from command-line arguments."""
    deployment_yaml = f"""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-deployment
spec:
  replicas: 1
  selector:
    matchLabels:
      app: my-app
  template:
    metadata:
      labels:
        app: my-app
    spec:
      containers:
      - name: my-container
        image: {args.image}
        resources:
          requests:
            cpu: {args.cpu_request}
            memory: {args.memory_request}
          limits:
            cpu: {args.cpu_limit}
            memory: {args.memory_limit}
        ports:
        - containerPort: {args.ports}
"""

    service_yaml = f"""
apiVersion: v1
kind: Service
metadata:
  name: my-service
spec:
  selector:
    app: my-app
  ports:
  - protocol: TCP
    port: 80
    targetPort: {args.ports}
  type: LoadBalancer
"""

    scaled_object_yaml = f"""
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: my-scaled-object
spec:
  scaleTargetRef:
    name: my-deployment
  pollingInterval: 15
  cooldownPeriod: 30
  maxReplicaCount: 10
  triggers:
  - type: cpu
    metadata:
      type: Utilization
      value: "50"
"""

    # Apply YAMLs to the cluster
    try:
        kubectl_apply(deployment_yaml)
        kubectl_apply(service_yaml)
        
        # Check if KEDA is installed before applying ScaledObject
        if check_keda_installed():
            kubectl_apply(scaled_object_yaml)
            print("Deployment, service, and KEDA ScaledObject created successfully.")
        else:
            print("Deployment and service created successfully. KEDA is not installed, skipping ScaledObject creation.")
    except Exception as e:
        print(f"Failed to create resources: {e}")
    """Create a Kubernetes deployment with KEDA scaling from command-line arguments."""
    deployment_yaml = f"""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-deployment
spec:
  replicas: 1
  selector:
    matchLabels:
      app: my-app
  template:
    metadata:
      labels:
        app: my-app
    spec:
      containers:
      - name: my-container
        image: {args.image}
        resources:
          requests:
            cpu: {args.cpu_request}
            memory: {args.memory_request}
          limits:
            cpu: {args.cpu_limit}
            memory: {args.memory_limit}
        ports:
        - containerPort: {args.ports}
"""

    service_yaml = f"""
apiVersion: v1
kind: Service
metadata:
  name: my-service
spec:
  selector:
    app: my-app
  ports:
  - protocol: TCP
    port: 80
    targetPort: {args.ports}
  type: LoadBalancer
"""

    scaled_object_yaml = f"""
apiVersion: keda.k8s.io/v1alpha1
kind: ScaledObject
metadata:
  name: my-scaled-object
spec:
  scaleTargetRef:
    deploymentName: my-deployment # must be in the same namespace as the ScaledObject
    containerName: my-container  #Optional. Default: deployment.spec.template.spec.containers[0]
  pollingInterval: 30  # Optional. Default: 30 seconds
  cooldownPeriod:  300 # Optional. Default: 300 seconds
  minReplicaCount: 0   # Optional. Default: 0
  maxReplicaCount: 100 # Optional. Default: 100
  triggers:
triggers:
- type: kafka
  metadata:
    bootstrapServers: kafka.svc:9092
    consumerGroup: my-group
    topic: test-topic
    lagThreshold: '5'
    activationLagThreshold: '3'
    offsetResetPolicy: latest
    allowIdleConsumers: false
    scaleToZeroOnInvalidOffset: false
    excludePersistentLag: false
    limitToPartitionsWithLag: false
    version: 1.0.0
    partitionLimitation: '1,2,10-20,31'
    sasl: plaintext
    tls: enable
    unsafeSsl: 'false'
"""

    # Apply YAMLs to the cluster
    try:
        for yaml_content in [deployment_yaml, service_yaml, scaled_object_yaml]:
            kubectl_apply(yaml_content)
        print("Deployment, service, and KEDA ScaledObject created successfully.")
    except Exception as e:
        print(f"Failed to create resources: {e}")

def create_deployment_from_files(file_path):
    """Create Kubernetes resources from manifest files."""
    if os.path.isfile(file_path):
        files = [file_path]
    elif os.path.isdir(file_path):
        files = [os.path.join(file_path, f) for f in os.listdir(file_path) if f.endswith('.yaml') or f.endswith('.yml')]
    else:
        print(f"Invalid file or directory path: {file_path}")
        return

    for file in files:
        try:
            with open(file, 'r') as f:
                docs = yaml.safe_load_all(f)
                for doc in docs:
                    kubectl_apply(yaml.dump(doc))
            print(f"Applied manifest from {file}")
        except Exception as e:
            print(f"Failed to apply manifest from {file}: {e}")

def kubectl_apply(yaml_content):
    """Apply Kubernetes YAML using kubectl."""
    try:
        result = subprocess.run(["kubectl", "apply", "-f", "-"], input=yaml_content, text=True, capture_output=True, check=True)
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error applying Kubernetes YAML: {e}")
        print(f"Error output: {e.stderr}")
        raise

def check_keda_installed():
    """Check if KEDA is installed in the cluster."""
    try:
        result = subprocess.run(["kubectl", "get", "crd", "scaledobjects.keda.sh"], capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False
    """Apply Kubernetes YAML using kubectl."""
    try:
        subprocess.run(["kubectl", "apply", "-f", "-"], input=yaml_content, text=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error applying Kubernetes YAML: {e}")
        raise

def get_deployment_status(deployment_name):
    """Retrieve the health status of a deployment."""
    try:
        config.load_kube_config()
        v1 = client.AppsV1Api()
        deployment = v1.read_namespaced_deployment(deployment_name, "default")
        print(f"Deployment {deployment_name} status: {deployment.status}")
    except ApiException as e:
        print(f"Error retrieving deployment status: {e}")

def main():
    parser = argparse.ArgumentParser(description="Kubernetes Automation Script")
    parser.add_argument('--context', required=True, help='Kubernetes context to use')
    parser.add_argument('--action', required=True, choices=['connect', 'install-helm', 'install-keda', 'create-deployment', 'get-status'], help='Action to perform')
    parser.add_argument('--image', help='Docker image for deployment')
    parser.add_argument('--cpu-request', help='CPU request for deployment')
    parser.add_argument('--memory-request', help='Memory request for deployment')
    parser.add_argument('--cpu-limit', help='CPU limit for deployment')
    parser.add_argument('--memory-limit', help='Memory limit for deployment')
    parser.add_argument('--ports', help='Ports to expose')
    parser.add_argument('--event-source', help='Event source for KEDA scaling')
    parser.add_argument('--deployment-name', help='Name of the deployment for status check')
    parser.add_argument('--file', help='file /path of file')

    args = parser.parse_args()

    try:
        connect_to_cluster(args.context)

        if args.action == 'install-helm':
            install_helm()
        elif args.action == 'install-keda':
            install_keda()
        elif args.action == 'create-deployment':
            if args.file:
                create_deployment_from_files(args.file)
            elif all([args.image, args.cpu_request, args.memory_request, args.cpu_limit, args.memory_limit, args.ports, args.event_source]):
                create_deployment_from_args(args)
            else:
                print("Either provide --file or all deployment parameters.")
                exit(1)
        elif args.action == 'get-status':
            if not args.deployment_name:
                print("Deployment name is required for status check.")
                exit(1)
            get_deployment_status(args.deployment_name)
    except Exception as e:
        print(f"An error occurred: {e}")
        exit(1)

if __name__ == "__main__":
    main()