import base64
import os
import subprocess
import time

from kubernetes import config, client, watch

KUBE_SYSTEM = "kube-system"
META_URL = os.getenv("JUICEFS_META_URL") or ""
ACCESS_KEY = os.getenv("JUICEFS_ACCESS_KEY") or ""
SECRET_KEY = os.getenv("JUICEFS_SECRET_KEY") or ""
STORAGE = os.getenv("JUICEFS_STORAGE") or ""
BUCKET = os.getenv("JUICEFS_BUCKET") or ""
TOKEN = os.getenv("JUICEFS_TOKEN")
RESOURCE_PREFIX = "ce-" if TOKEN is None else "ee-"

SECRET_NAME = os.getenv("JUICEFS_NAME") or "ce-juicefs-secret"
STORAGECLASS_NAME = "ce-juicefs-sc" if TOKEN is None else "ee-juicefs-sc"
SECRETs = []
STORAGECLASSs = []
DEPLOYMENTs = []
PVCs = []
PVs = []


class Secret:
    def __init__(self, *, secret_name):
        self.secret_name = secret_name
        self.namespace = KUBE_SYSTEM
        self.meta_url = META_URL
        self.access_key = ACCESS_KEY
        self.secret_key = SECRET_KEY
        self.storage_name = STORAGE
        self.bucket = BUCKET
        self.token = TOKEN

    def create(self):
        if self.meta_url != "":
            data = {
                "name": base64.b64encode(self.secret_name.encode('utf-8')).decode("utf-8"),
                "metaurl": base64.b64encode(self.meta_url.encode('utf-8')).decode("utf-8"),
                "access-key": base64.b64encode(self.access_key.encode('utf-8')).decode("utf-8"),
                "secret-key": base64.b64encode(self.secret_key.encode('utf-8')).decode("utf-8"),
                "storage": base64.b64encode(self.storage_name.encode('utf-8')).decode("utf-8"),
                "bucket": base64.b64encode(self.bucket.encode('utf-8')).decode("utf-8"),
            }
        else:
            data = {
                "name": base64.b64encode(self.secret_name.encode('utf-8')).decode("utf-8"),
                "token": base64.b64encode(self.token.encode('utf-8')).decode("utf-8"),
                "accesskey": base64.b64encode(self.access_key.encode('utf-8')).decode("utf-8"),
                "secretkey": base64.b64encode(self.secret_key.encode('utf-8')).decode("utf-8"),
                "storage": base64.b64encode(self.storage_name.encode('utf-8')).decode("utf-8"),
                "bucket": base64.b64encode(self.bucket.encode('utf-8')).decode("utf-8"),
            }
        sec = client.V1Secret(
            api_version="v1",
            kind="Secret",
            metadata=client.V1ObjectMeta(name=self.secret_name),
            data=data
        )
        client.CoreV1Api().create_namespaced_secret(namespace=self.namespace, body=sec)
        SECRETs.append(self)

    def delete(self):
        client.CoreV1Api().delete_namespaced_secret(name=self.secret_name, namespace=self.namespace)
        SECRETs.remove(self)


class StorageClass:
    def __init__(self, *, name, secret_name):
        self.name = name
        self.secret_name = secret_name
        self.secret_namespace = KUBE_SYSTEM

    def create(self):
        sc = client.V1StorageClass(
            api_version="storage.k8s.io/v1",
            kind="StorageClass",
            metadata=client.V1ObjectMeta(name=self.name),
            provisioner="csi.juicefs.com",
            reclaim_policy="Delete",
            volume_binding_mode="Immediate",
            parameters={
                "csi.storage.k8s.io/node-publish-secret-name": self.secret_name,
                "csi.storage.k8s.io/node-publish-secret-namespace": self.secret_namespace,
                "csi.storage.k8s.io/provisioner-secret-name": self.secret_name,
                "csi.storage.k8s.io/provisioner-secret-namespace": self.secret_namespace,
            }
        )
        client.StorageV1Api().create_storage_class(body=sc)
        STORAGECLASSs.append(self)

    def delete(self):
        client.StorageV1Api().delete_storage_class(name=self.name)
        STORAGECLASSs.remove(self)


class PVC:
    def __init__(self, *, name, access_mode, storage_name):
        self.name = RESOURCE_PREFIX + name
        self.namespace = "default"
        self.access_mode = access_mode
        self.storage_class = storage_name

    def create(self):
        spec = client.V1PersistentVolumeClaimSpec(
            access_modes=[self.access_mode],
            resources=client.V1ResourceRequirements(
                requests={"storage": "1Gi"}
            )
        )
        if self.storage_class != "":
            spec.storage_class_name = self.storage_class
        pvc = client.V1PersistentVolumeClaim(
            api_version="v1",
            kind="PersistentVolumeClaim",
            metadata=client.V1ObjectMeta(name=self.name),
            spec=spec
        )
        client.CoreV1Api().create_namespaced_persistent_volume_claim(namespace=self.namespace, body=pvc)
        PVCs.append(self)

    def delete(self):
        client.CoreV1Api().delete_namespaced_persistent_volume_claim(name=self.name, namespace=self.namespace)
        PVCs.remove(self)

    def get_volume_id(self):
        p = client.CoreV1Api().read_namespaced_persistent_volume_claim(name=self.name, namespace=self.namespace)
        pv_name = p.spec.volume_name
        pv = client.CoreV1Api().read_persistent_volume(name=pv_name)
        return pv.spec.csi.volume_handle


class PV:
    def __init__(self, *, name, access_mode, volume_handle, secret_name):
        self.name = RESOURCE_PREFIX + name
        self.access_mode = access_mode
        self.volume_handle = volume_handle
        self.secret_name = secret_name
        self.secret_namespace = KUBE_SYSTEM

    def create(self):
        spec = client.V1PersistentVolumeSpec(
            access_modes=[self.access_mode],
            capacity={"storage": "10Pi"},
            volume_mode="Filesystem",
            persistent_volume_reclaim_policy="Delete",
            csi=client.V1CSIPersistentVolumeSource(
                driver="csi.juicefs.com",
                fs_type="juicefs",
                volume_handle=self.volume_handle,
                node_publish_secret_ref=client.V1SecretReference(
                    name=self.secret_name,
                    namespace=self.secret_namespace
                ),
            )
        )
        pv = client.V1PersistentVolume(
            api_version="v1",
            kind="PersistentVolume",
            metadata=client.V1ObjectMeta(name=self.name),
            spec=spec
        )
        client.CoreV1Api().create_persistent_volume(body=pv)
        PVs.append(self)

    def delete(self):
        client.CoreV1Api().delete_persistent_volume(name=self.name)
        PVs.remove(self)

    def get_volume_id(self):
        p = client.CoreV1Api().read_persistent_volume(name=self.name)
        return p.spec.csi.volume_handle


class Deployment:
    def __init__(self, *, name, pvc, replicas):
        self.name = RESOURCE_PREFIX + name
        self.namespace = "default"
        self.image = "centos"
        self.pvc = pvc
        self.replicas = replicas

    def create(self):
        container = client.V1Container(
            name="app",
            image="centos",
            command=["/bin/sh"],
            args=["-c", "while true; do echo $(date -u) >> /data/out.txt; sleep 5; done"],
            volume_mounts=[client.V1VolumeMount(
                name="juicefs-pv",
                mount_path="/data"
            )]
        )
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels={"deployment": self.name}),
            spec=client.V1PodSpec(
                containers=[container],
                volumes=[client.V1Volume(
                    name="juicefs-pv",
                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(claim_name=self.pvc)
                )]),
        )
        deploySpec = client.V1DeploymentSpec(
            replicas=self.replicas,
            template=template,
            selector={"matchLabels": {"deployment": self.name}}
        )
        deploy = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(name=self.name),
            spec=deploySpec,
        )
        client.AppsV1Api().create_namespaced_deployment(namespace=self.namespace, body=deploy)
        DEPLOYMENTs.append(self)

    def update_replicas(self, replicas):
        deployment = client.AppsV1Api().read_namespaced_deployment(name=self.name, namespace=self.namespace)
        deployment.spec.replicas = replicas
        client.AppsV1Api().patch_namespaced_deployment(name=self.name, namespace=self.namespace, body=deployment)

    def delete(self):
        client.AppsV1Api().delete_namespaced_deployment(name=self.name, namespace=self.namespace)
        DEPLOYMENTs.remove(self)


class Pod:
    def __init__(self, name, deployment_name, replicas, namespace="default"):
        self.name = name
        self.namespace = namespace
        self.deployment = deployment_name
        self.pods = []
        self.replicas = replicas

    def watch_for_success(self):
        v1 = client.CoreV1Api()
        w = watch.Watch()
        for event in w.stream(v1.list_pod_for_all_namespaces, timeout_seconds=5 * 60):
            resource = event['object']
            if resource.metadata.namespace != "default":
                continue
            if self.name == "" and resource.metadata.labels.get("deployment") != self.deployment:
                continue
            if self.name != "" and resource.metadata.name != self.name:
                continue
            print("Event: %s %s" % (event['type'], event['object'].metadata.name))
            if self.__is_pod_ready(resource):
                if self.name == "":
                    self.pods.append(resource)
                    if len(self.pods) == self.replicas:
                        self.pods = []
                        return True
                else:
                    return True
        return False

    @staticmethod
    def __is_pod_ready(resource):
        if resource.status.phase.lower() != "running":
            print("Pod {} status phase: {}".format(resource.metadata.name, resource.status.phase))
            return False
        conditions = resource.status.conditions
        for c in conditions:
            if c.status != "True":
                return False
        print("Pod {} status is ready.".format(resource.metadata.name))
        return True

    def watch_for_delete(self, num):
        v1 = client.CoreV1Api()
        w = watch.Watch()
        for event in w.stream(v1.list_pod_for_all_namespaces, timeout_seconds=5 * 60):
            resource = event['object']
            message_type = event['type']
            if resource.metadata.namespace != "default":
                continue
            if self.name == "" and resource.metadata.labels.get("deployment") != self.deployment:
                continue
            if self.name != "" and resource.metadata.name != self.name:
                continue
            print("Event: %s %s" % (event['type'], event['object'].metadata.name))
            if message_type == "DELETED":
                if self.name == "":
                    self.pods.append(resource)
                    if len(self.pods) == num:
                        self.pods = []
                        return True
                else:
                    return True
        return False

    def is_deleted(self):
        try:
            po = client.CoreV1Api().read_namespaced_pod(self.name, self.namespace)
        except client.exceptions.ApiException as e:
            if e.status == 404:
                return True
            raise e
        return po.metadata.deletion_timestamp != ""

    def get_log(self, container_name):
        return client.CoreV1Api().read_namespaced_pod_log(self.name, self.namespace, container=container_name)


def check_mount_point(volume_id, is_static=False):
    print("mount /jfs.")
    if TOKEN is None:
        subprocess.run(["sudo", "juicefs", "mount", "-d", META_URL, "/jfs"])
    else:
        subprocess.run(
            ["sudo", "/usr/bin/juicefs", "auth", f"--token={TOKEN}", f"--accesskey={ACCESS_KEY}",
             f"--secretkey={SECRET_KEY}", f"--bucket={BUCKET}", SECRET_NAME])
        subprocess.run(["sudo", "/usr/bin/juicefs", "mount", "-d", SECRET_NAME, "/jfs"])

    check_path = f"/jfs/{volume_id}/out.txt" if not is_static else "/jfs/out.txt"
    for i in range(0, 60):
        try:
            f = open(check_path)
        except FileNotFoundError:
            print("Can't find file: {}".format(check_path))
            time.sleep(5)
            continue
        content = f.read(1)
        if content is not None and content != "":
            f.close()
            print("umount /jfs.")
            subprocess.run(["sudo", "umount", "/jfs"])
            return True
        time.sleep(5)
        f.close()
    print("umount /jfs.")
    subprocess.run(["sudo", "umount", "/jfs"])
    return False


def get_mount_pod_name(volume_id):
    nodes = client.CoreV1Api().list_node()
    node_name = nodes.items[0].metadata.name
    return "juicefs-{}-{}".format(node_name, volume_id)


def check_mount_pod_refs(pod_name, replicas):
    pod = client.CoreV1Api().read_namespaced_pod(name=pod_name, namespace=KUBE_SYSTEM)
    annotations = pod.metadata.annotations
    if annotations is None:
        if replicas == 0:
            return True
        else:
            return False
    num = 0
    for k in annotations.keys():
        if k.startswith("juicefs-"):
            num += 1
    return num == replicas


def deploy_secret_and_sc():
    print("deploy secret & storageClass..")
    secret = Secret(secret_name=SECRET_NAME)
    secret.create()
    sc = StorageClass(name=STORAGECLASS_NAME, secret_name=secret.secret_name)
    sc.create()


def tear_down():
    try:
        for secret in SECRETs:
            secret.delete()
        for pvc in PVCs:
            pvc.delete()
        for sc in STORAGECLASSs:
            sc.delete()
        for pv in PVs:
            pv.delete()
        for deploy in DEPLOYMENTs:
            deploy.delete()
    except Exception as e:
        print("error in tear down: {}".format(e))


###### test case in ci ######
def test_deployment_using_storage_rw():
    print("[test case] deployment using storageClass with rwm begin..")
    # deploy pvc
    pvc = PVC(name="pvc-dynamic-rw", access_mode="ReadWriteMany", storage_name=STORAGECLASS_NAME)
    print("deploy pvc {}".format(pvc.name))
    pvc.create()

    # deploy pod
    deployment = Deployment(name="app-dynamic-rw", pvc=pvc.name, replicas=1)
    print("deploy deployment {}".format(deployment.name))
    deployment.create()
    pod = Pod(name="", deployment_name=deployment.name, replicas=deployment.replicas)
    print("watch for pods of {} for success.".format(deployment.name))
    result = pod.watch_for_success()
    if not result:
        csi_node_name = os.getenv("JUICEFS_CSI_NODE_POD")
        mount_pod = Pod(name=csi_node_name, deployment_name="", replicas=1, namespace=KUBE_SYSTEM)
        print("get csi node log:")
        print(mount_pod.get_log("juicefs-plugin"))
        raise Exception("pods of deployment {} are not ready within 5 min.".format(deployment.name))

    # check mount point
    print("check mount point..")
    volume_id = pvc.get_volume_id()
    print("get volume_id {}".format(volume_id))
    result = check_mount_point(volume_id)
    if not result:
        raise Exception("mount point of /jfs/{}/out.txt are not ready within 5 min.".format(volume_id))
    print("test pass.")
    return


def test_deployment_using_storage_ro():
    print("[test case] deployment using storageClass with rom begin..")
    # deploy pvc
    pvc = PVC(name="pvc-dynamic-ro", access_mode="ReadOnlyMany", storage_name=STORAGECLASS_NAME)
    print("deploy pvc {}".format(pvc.name))
    pvc.create()

    # deploy pod
    deployment = Deployment(name="app-dynamic-ro", pvc=pvc.name, replicas=1)
    print("deploy deployment {}".format(deployment.name))
    deployment.create()
    pod = Pod(name="", deployment_name=deployment.name, replicas=deployment.replicas)
    print("watch for pods of {} for success.".format(deployment.name))
    result = pod.watch_for_success()
    if not result:
        raise Exception("pods of deployment {} are not ready within 5 min.".format(deployment.name))

    print("test pass.")
    return


def test_deployment_use_pv_rw():
    print("[test case] deployment using pv with rwm begin..")
    # deploy pvc
    pvc = PVC(name="pvc-static-rw", access_mode="ReadWriteMany", storage_name="")
    print("deploy pvc {}".format(pvc.name))
    pvc.create()

    pv = PV(name="pv-rw", access_mode="ReadWriteMany", volume_handle="pv-rw", secret_name=SECRET_NAME)
    print("deploy pv {}".format(pv.name))
    pv.create()

    # deploy pod
    deployment = Deployment(name="app-static-rw", pvc=pvc.name, replicas=1)
    print("deploy deployment {}".format(deployment.name))
    deployment.create()
    pod = Pod(name="", deployment_name=deployment.name, replicas=deployment.replicas)
    print("watch for pods of {} for success.".format(deployment.name))
    result = pod.watch_for_success()
    if not result:
        raise Exception("pods of deployment {} are not ready within 5 min.".format(deployment.name))

    # check mount point
    # print("check mount point..")
    # volume_id = pv.get_volume_id()
    # print("get volume_id {}".format(volume_id))
    # result = check_mount_point(volume_id, True)
    # if not result:
    #     raise Exception("mount point of /jfs/out.txt are not ready within 5 min.")

    print("test pass.")
    return


def test_deployment_use_pv_ro():
    print("[test case] deployment using pv with rwo begin..")
    # deploy pvc
    pvc = PVC(name="pvc-static-ro", access_mode="ReadOnlyMany", storage_name="")
    print("deploy pvc {}".format(pvc.name))
    pvc.create()

    pv = PV(name="pv-ro", access_mode="ReadOnlyMany", volume_handle="pv-ro", secret_name=SECRET_NAME)
    print("deploy pv {}".format(pv.name))
    pv.create()

    # deploy pod
    deployment = Deployment(name="app-static-ro", pvc=pvc.name, replicas=1)
    print("deploy deployment {}".format(deployment.name))
    deployment.create()
    pod = Pod(name="", deployment_name=deployment.name, replicas=deployment.replicas)
    print("watch for pods of {} for success.".format(deployment.name))
    result = pod.watch_for_success()
    if not result:
        raise Exception("pods of deployment {} are not ready within 5 min.".format(deployment.name))

    print("test pass.")
    return


def test_delete_one():
    print("[test case] deployment with 3 replicas begin..")
    # deploy pvc
    pvc = PVC(name="pvc-replicas", access_mode="ReadWriteMany", storage_name=STORAGECLASS_NAME)
    print("deploy pvc {}".format(pvc.name))
    pvc.create()

    # deploy pod
    deployment = Deployment(name="app-replicas", pvc=pvc.name, replicas=3)
    print("deploy deployment {}".format(deployment.name))
    deployment.create()
    pod = Pod(name="", deployment_name=deployment.name, replicas=deployment.replicas)
    print("watch for pods of {} for success.".format(deployment.name))
    result = pod.watch_for_success()
    if not result:
        raise Exception("pods of deployment {} are not ready within 5 min.".format(deployment.name))

    volume_id = pvc.get_volume_id()
    print("get volume_id {}".format(volume_id))

    # check mount pod refs
    mount_pod_name = get_mount_pod_name(volume_id)
    print("check mount pod {} refs.".format(mount_pod_name))
    result = check_mount_pod_refs(mount_pod_name, 3)
    if not result:
        raise Exception("mount pod {} does not have {} juicefs- refs.".format(mount_pod_name, 3))

    # update replicas = 1
    print("set deployment {} replicas to 1".format(deployment.name))
    deployment.update_replicas(1)
    pod = Pod(name="", deployment_name=deployment.name, replicas=deployment.replicas)
    print("watch for pods of deployment {} for delete.".format(deployment.name))
    result = pod.watch_for_delete(2)
    if not result:
        raise Exception("pods of deployment {} are not delete within 5 min.".format(deployment.name))

    # check mount pod refs
    result = check_mount_pod_refs(mount_pod_name, 1)
    print("check mount pod {} refs.".format(mount_pod_name))
    if not result:
        raise Exception("mount pod {} does not have {} juicefs- refs.".format(mount_pod_name, 1))

    print("test pass.")
    return


def test_delete_all():
    print("[test case] deployment and delete it begin..")
    # deploy pvc
    pvc = PVC(name="pvc-delete-deploy", access_mode="ReadWriteMany", storage_name=STORAGECLASS_NAME)
    print("deploy pvc {}".format(pvc.name))
    pvc.create()

    # deploy pod
    deployment = Deployment(name="app-delete-deploy", pvc=pvc.name, replicas=3)
    print("deploy deployment {}".format(deployment.name))
    deployment.create()
    pod = Pod(name="", deployment_name=deployment.name, replicas=deployment.replicas)
    print("watch for pods of {} for success.".format(deployment.name))
    result = pod.watch_for_success()
    if not result:
        raise Exception("pods of deployment {} are not ready within 5 min.".format(deployment.name))

    volume_id = pvc.get_volume_id()
    print("get volume_id {}".format(volume_id))

    # check mount pod refs
    mount_pod_name = get_mount_pod_name(volume_id)
    print("check mount pod {} refs.".format(mount_pod_name))
    result = check_mount_pod_refs(mount_pod_name, 3)
    if not result:
        raise Exception("mount pod {} does not have {} juicefs- refs.".format(mount_pod_name, 3))

    # delete deploy
    print("delete deployment {}".format(deployment.name))
    deployment.delete()
    pod = Pod(name="", deployment_name=deployment.name, replicas=deployment.replicas)
    print("watch for pods of deployment {} for delete.".format(deployment.name))
    result = pod.watch_for_delete(3)
    if not result:
        raise Exception("pods of deployment {} are not delete within 5 min.".format(deployment.name))

    # check mount pod is delete or not
    print("check mount pod {} is deleted or not.".format(mount_pod_name))
    pod = Pod(name=mount_pod_name, deployment_name="", replicas=1)
    result = pod.is_deleted()
    if not result:
        raise Exception("mount pod {} does not been deleted within 5 min.".format(mount_pod_name))

    print("test pass.")
    return


if __name__ == "__main__":
    config.load_kube_config()
    try:
        deploy_secret_and_sc()
        test_deployment_using_storage_rw()
        # test_deployment_using_storage_ro()
        # test_deployment_use_pv_rw()
        # test_deployment_use_pv_ro()
        # test_delete_one()
        # test_delete_all()
    finally:
        tear_down()
