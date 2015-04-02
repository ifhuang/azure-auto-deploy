__author__ = 'Yifu Huang'

from src.azureformation.azureoperation.resourceBase import(
    ResourceBase,
)
from src.azureformation.azureoperation.utility import (
    AZURE_FORMATION,
    ASYNC_TICK,
    ASYNC_LOOP,
    DEPLOYMENT_TICK,
    VIRTUAL_MACHINE_TICK,
    VIRTUAL_MACHINE_LOOP,
    MDL_CLS_FUNC,
    commit_azure_log,
    commit_azure_deployment,
    commit_azure_virtual_machine,
    commit_azure_endpoint,
    commit_virtual_environment,
    contain_azure_deployment,
    contain_azure_virtual_machine,
    delete_azure_deployment,
    delete_azure_virtual_machine,
    get_azure_virtual_machine_status,
    update_azure_virtual_machine_status,
    update_virtual_environment_status,
    update_virtual_environment_private_ip,
    run_job,
)
from src.azureformation.enum import (
    DEPLOYMENT,
    VIRTUAL_MACHINE,
    ALOperation,
    ALStatus,
    ADStatus,
    AVMStatus,
    VEProvider,
    VERemoteProvider,
    VEStatus,
)
from src.azureformation.log import (
    log,
)
import json


# todo take care of resource check
# todo support batch operations
class VirtualMachine(ResourceBase):
    """
    Virtual machine is azure virtual machine with its azure deployment
    """
    CREATE_DEPLOYMENT_ERROR = [
        '%s [%s] %s',
        '%s [%s] subscription not enough',
        '%s [%s] wait for async fail',
    ]
    CREATE_DEPLOYMENT_INFO = [
        '%s [%s] created',
        '%s [%s] exist and created by %s before',
        '%s [%s] exist but not created by %s before',
    ]
    CREATE_VIRTUAL_MACHINE_ERROR = [
        '%s [%s] %s',
        '%s [%s] subscription not enough',
        '%s [%s] wait for async fail',
        '%s [%s] wait for async fail (update network config)',
        '%s [%s] exist but not created by %s before',
    ]
    CREATE_VIRTUAL_MACHINE_INFO = [
        '%s [%s] created',
        '%s [%s] exist and created by %s before',
    ]
    STOP_VIRTUAL_MACHINE_ERROR = [
        '%s [%s] %s',
        '%s [%s] need status %s but now status %s',
        '%s [%s] wait for async fail',
        '%s [%s] wait for virtual machine fail',
    ]
    STOP_VIRTUAL_MACHINE_INFO = [
        '%s [%s] %s',
        '%s [%s] %s and by %s before',
        '%s [%s] %s but not by %s before',
    ]
    START_VIRTUAL_MACHINE_ERROR = [
        '%s [%s] %s',
        '%s [%s] wait for async fail',
        '%s [%s] wait for virtual machine fail',
    ]
    START_VIRTUAL_MACHINE_INFO = [
        '%s [%s] started',
        '%s [%s] started by %s before',
        '%s [%s] started but not by %s before',
    ]
    SIZE_CORE_MAP = {
        'a0': 1,
        'basic_a0': 1,
        'a1': 1,
        'basic_a1': 1,
        'a2': 2,
        'basic_a2': 2,
        'a3': 4,
        'basic_a3': 4,
        'a4': 8,
        'basic_a4': 8,
        'extra small': 1,
        'small': 1,
        'medium': 2,
        'large': 4,
        'extra large': 8,
        'a5': 2,
        'a6': 4,
        'a7': 8,
        'a8': 8,
        'a9': 16,
        'standard_d1': 1,
        'standard_d2': 2,
        'standard_d3': 4,
        'standard_d4': 8,
        'standard_d11': 2,
        'standard_d12': 4,
        'standard_d13': 8,
        'standard_d14': 16,
        'standard_ds1': 1,
        'standard_ds2': 2,
        'standard_ds3': 4,
        'standard_ds4': 8,
        'standard_ds11': 2,
        'standard_ds12': 4,
        'standard_ds13': 8,
        'standard_ds14': 16,
        'standard_g1': 2,
        'standard_g2': 4,
        'standard_g3': 8,
        'standard_g4': 16,
        'standard_g5': 32,
    }
    VIRTUAL_MACHINE_NAME_BASE = '%s-%d'

    def __init__(self, azure_key_id):
        super(VirtualMachine, self).__init__(azure_key_id)

    def create_virtual_machine(self, experiment_id, template_unit):
        """
        0. Prerequisites: a. storage account and cloud service exist in both azure and database;
                          b. input parameters are correct;
        1. If deployment not exist in azure subscription, then create virtual machine with deployment
           Else reuse deployment in azure subscription
        2. If virtual machine not exist in azure subscription, then add virtual machine to deployment
           Else reuse virtual machine in azure subscription
        :return:
        """
        commit_azure_log(experiment_id, ALOperation.CREATE_DEPLOYMENT, ALStatus.START)
        commit_azure_log(experiment_id, ALOperation.CREATE_VIRTUAL_MACHINE, ALStatus.START)
        deployment_slot = template_unit.get_deployment_slot()
        # avoid virtual machine name conflict on same name in template
        virtual_machine_name = self.VIRTUAL_MACHINE_NAME_BASE % (template_unit.get_virtual_machine_name(),
                                                                 experiment_id)
        virtual_machine_size = template_unit.get_virtual_machine_size()
        if self.subscription.get_available_core_count() < self.SIZE_CORE_MAP[virtual_machine_size.lower()]:
            m = self.CREATE_DEPLOYMENT_ERROR[1] % (DEPLOYMENT, deployment_slot)
            commit_azure_log(experiment_id, ALOperation.CREATE_DEPLOYMENT, ALStatus.FAIL, m, 1)
            log.error(m)
            m = self.CREATE_VIRTUAL_MACHINE_ERROR[1] % (VIRTUAL_MACHINE, virtual_machine_name)
            commit_azure_log(experiment_id, ALOperation.CREATE_VIRTUAL_MACHINE, ALStatus.FAIL, m, 1)
            log.error(m)
            return False
        cloud_service_name = template_unit.get_cloud_service_name()
        vm_image_name = template_unit.get_vm_image_name()
        system_config = template_unit.get_system_config()
        os_virtual_hard_disk = template_unit.get_os_virtual_hard_disk()
        # avoid duplicate deployment in azure subscription
        if self.service.deployment_exists(cloud_service_name, deployment_slot):
            # use deployment name from azure subscription
            deployment_name = self.service.get_deployment_name(cloud_service_name, deployment_slot)
            if contain_azure_deployment(cloud_service_name, deployment_slot):
                m = self.CREATE_DEPLOYMENT_INFO[1] % (DEPLOYMENT, deployment_name, AZURE_FORMATION)
                commit_azure_log(experiment_id, ALOperation.CREATE_DEPLOYMENT, ALStatus.END, m, 1)
            else:
                m = self.CREATE_DEPLOYMENT_INFO[2] % (DEPLOYMENT, deployment_name, AZURE_FORMATION)
                commit_azure_deployment(deployment_name,
                                        deployment_slot,
                                        ADStatus.RUNNING,
                                        cloud_service_name,
                                        experiment_id)
                commit_azure_log(experiment_id, ALOperation.CREATE_DEPLOYMENT, ALStatus.END, m, 2)
            log.debug(m)
            # avoid duplicate virtual machine in azure subscription
            if self.service.virtual_machine_exists(cloud_service_name, deployment_name, virtual_machine_name):
                if contain_azure_virtual_machine(cloud_service_name, deployment_name, virtual_machine_name):
                    m = self.CREATE_VIRTUAL_MACHINE_INFO[1] % (VIRTUAL_MACHINE, virtual_machine_name, AZURE_FORMATION)
                    commit_azure_log(experiment_id, ALOperation.CREATE_VIRTUAL_MACHINE, ALStatus.END, m, 1)
                    log.debug(m)
                else:
                    m = self.CREATE_VIRTUAL_MACHINE_ERROR[4] % (VIRTUAL_MACHINE, virtual_machine_name, AZURE_FORMATION)
                    commit_azure_log(experiment_id, ALOperation.CREATE_VIRTUAL_MACHINE, ALStatus.FAIL, m, 4)
                    log.error(m)
                    return False
            else:
                # delete old azure virtual machine, cascade delete old azure endpoint
                delete_azure_virtual_machine(cloud_service_name, deployment_name, virtual_machine_name)
                network_config = template_unit.get_network_config(self.service, False)
                try:
                    result = self.service.add_virtual_machine(cloud_service_name,
                                                              deployment_name,
                                                              virtual_machine_name,
                                                              system_config,
                                                              os_virtual_hard_disk,
                                                              network_config,
                                                              virtual_machine_size,
                                                              vm_image_name)
                except Exception as e:
                    m = self.CREATE_VIRTUAL_MACHINE_ERROR[0] % (VIRTUAL_MACHINE, virtual_machine_name, e.message)
                    commit_azure_log(experiment_id, ALOperation.CREATE_VIRTUAL_MACHINE, ALStatus.FAIL, m, 0)
                    log.error(e)
                    return False
                # query async operation status
                run_job(MDL_CLS_FUNC[2],
                        (self.azure_key_id, ),
                        (result.request_id,
                         MDL_CLS_FUNC[6], (self.azure_key_id, ), (experiment_id, template_unit),
                         MDL_CLS_FUNC[7], (self.azure_key_id, ), (experiment_id, template_unit)))
        else:
            # delete old azure deployment, cascade delete old azure virtual machine and azure endpoint
            delete_azure_deployment(cloud_service_name, deployment_slot)
            # use deployment name from template
            deployment_name = template_unit.get_deployment_name()
            virtual_machine_label = template_unit.get_virtual_machine_label()
            network_config = template_unit.get_network_config(self.service, False)
            try:
                result = self.service.create_virtual_machine_deployment(cloud_service_name,
                                                                        deployment_name,
                                                                        deployment_slot,
                                                                        virtual_machine_label,
                                                                        virtual_machine_name,
                                                                        system_config,
                                                                        os_virtual_hard_disk,
                                                                        network_config,
                                                                        virtual_machine_size,
                                                                        vm_image_name)
            except Exception as e:
                m = self.CREATE_DEPLOYMENT_ERROR[0] % (DEPLOYMENT, deployment_slot, e.message)
                commit_azure_log(experiment_id, ALOperation.CREATE_DEPLOYMENT, ALStatus.FAIL, m, 0)
                m = self.CREATE_VIRTUAL_MACHINE_ERROR[0] % (VIRTUAL_MACHINE, virtual_machine_name, e.message)
                commit_azure_log(experiment_id, ALOperation.CREATE_VIRTUAL_MACHINE, ALStatus.FAIL, m, 0)
                log.error(e)
                return False
            # query async operation status
            run_job(MDL_CLS_FUNC[2],
                    (self.azure_key_id, ),
                    (result.request_id,
                     MDL_CLS_FUNC[13], (self.azure_key_id, ), (experiment_id, template_unit),
                     MDL_CLS_FUNC[14], (self.azure_key_id, ), (experiment_id, template_unit)))
        return True

    def create_virtual_machine_async_true_1(self, experiment_id, template_unit):
        cloud_service_name = template_unit.get_cloud_service_name()
        deployment_slot = template_unit.get_deployment_slot()
        deployment_name = self.service.get_deployment_name(cloud_service_name, deployment_slot)
        virtual_machine_name = self.VIRTUAL_MACHINE_NAME_BASE % (template_unit.get_virtual_machine_name(),
                                                                 experiment_id)
        # query virtual machine status
        run_job(MDL_CLS_FUNC[8],
                (self.azure_key_id, ),
                (cloud_service_name, deployment_name, virtual_machine_name, AVMStatus.READY_ROLE,
                 MDL_CLS_FUNC[9], (self.azure_key_id, ), (experiment_id, template_unit)),
                VIRTUAL_MACHINE_TICK)

    def create_virtual_machine_async_false_1(self, experiment_id, template_unit):
        virtual_machine_name = self.VIRTUAL_MACHINE_NAME_BASE % (template_unit.get_virtual_machine_name(),
                                                                 experiment_id)
        m = self.CREATE_VIRTUAL_MACHINE_ERROR[2] % (VIRTUAL_MACHINE, virtual_machine_name)
        commit_azure_log(experiment_id, ALOperation.CREATE_VIRTUAL_MACHINE, ALStatus.FAIL, m, 2)
        log.error(m)

    def create_virtual_machine_vm_true_1(self, experiment_id, template_unit):
        if template_unit.is_vm_image():
            cloud_service_name = template_unit.get_cloud_service_name()
            deployment_slot = template_unit.get_deployment_slot()
            deployment_name = self.service.get_deployment_name(cloud_service_name, deployment_slot)
            virtual_machine_name = self.VIRTUAL_MACHINE_NAME_BASE % (template_unit.get_virtual_machine_name(),
                                                                     experiment_id)
            network_config = template_unit.get_network_config(self.service, True)
            result = self.service.update_virtual_machine_network_config(cloud_service_name,
                                                                        deployment_name,
                                                                        virtual_machine_name,
                                                                        network_config)
            # query async operation status
            run_job(MDL_CLS_FUNC[2],
                    (self.azure_key_id, ),
                    (result.request_id,
                     MDL_CLS_FUNC[10], (self.azure_key_id, ), (experiment_id, template_unit),
                     MDL_CLS_FUNC[11], (self.azure_key_id, ), (experiment_id, template_unit)))
        else:
            self.__create_virtual_machine_helper(experiment_id, template_unit)

    def create_virtual_machine_async_true_2(self, experiment_id, template_unit):
        cloud_service_name = template_unit.get_cloud_service_name()
        deployment_slot = template_unit.get_deployment_slot()
        deployment_name = self.service.get_deployment_name(cloud_service_name, deployment_slot)
        virtual_machine_name = self.VIRTUAL_MACHINE_NAME_BASE % (template_unit.get_virtual_machine_name(),
                                                                 experiment_id)
        # query virtual machine status
        run_job(MDL_CLS_FUNC[8],
                (self.azure_key_id, ),
                (cloud_service_name, deployment_name, virtual_machine_name, AVMStatus.READY_ROLE,
                 MDL_CLS_FUNC[12], (self.azure_key_id, ), (experiment_id, template_unit)),
                VIRTUAL_MACHINE_TICK)

    def create_virtual_machine_async_false_2(self, experiment_id, template_unit):
        virtual_machine_name = self.VIRTUAL_MACHINE_NAME_BASE % (template_unit.get_virtual_machine_name(),
                                                                 experiment_id)
        m = self.CREATE_VIRTUAL_MACHINE_ERROR[3] % (VIRTUAL_MACHINE, virtual_machine_name)
        commit_azure_log(experiment_id, ALOperation.CREATE_VIRTUAL_MACHINE, ALStatus.FAIL, m, 3)
        log.error(m)

    def create_virtual_machine_vm_true_2(self, experiment_id, template_unit):
        self.__create_virtual_machine_helper(experiment_id, template_unit)

    def create_virtual_machine_async_true_3(self, experiment_id, template_unit):
        cloud_service_name = template_unit.get_cloud_service_name()
        deployment_name = template_unit.get_deployment_name()
        # query deployment status
        run_job(MDL_CLS_FUNC[15],
                (self.azure_key_id, ),
                (cloud_service_name, deployment_name,
                 MDL_CLS_FUNC[16], (self.azure_key_id, ), (experiment_id, template_unit)),
                DEPLOYMENT_TICK)

    def create_virtual_machine_async_false_3(self, experiment_id, template_unit):
        deployment_slot = template_unit.get_deployment_slot()
        virtual_machine_name = self.VIRTUAL_MACHINE_NAME_BASE % (template_unit.get_virtual_machine_name(),
                                                                 experiment_id)
        m = self.CREATE_DEPLOYMENT_ERROR[2] % (DEPLOYMENT, deployment_slot)
        commit_azure_log(experiment_id, ALOperation.CREATE_DEPLOYMENT, ALStatus.FAIL, m, 2)
        log.error(m)
        m = self.CREATE_VIRTUAL_MACHINE_ERROR[2] % (VIRTUAL_MACHINE, virtual_machine_name)
        commit_azure_log(experiment_id, ALOperation.CREATE_VIRTUAL_MACHINE, ALStatus.FAIL, m, 2)
        log.error(m)

    def create_virtual_machine_dm_true(self, experiment_id, template_unit):
        cloud_service_name = template_unit.get_cloud_service_name()
        deployment_slot = template_unit.get_deployment_slot()
        deployment_name = template_unit.get_deployment_name()
        virtual_machine_name = self.VIRTUAL_MACHINE_NAME_BASE % (template_unit.get_virtual_machine_name(),
                                                                 experiment_id)
        m = self.CREATE_DEPLOYMENT_INFO[0] % (DEPLOYMENT, deployment_slot)
        commit_azure_deployment(deployment_name,
                                deployment_slot,
                                ADStatus.RUNNING,
                                cloud_service_name,
                                experiment_id)
        commit_azure_log(experiment_id, ALOperation.CREATE_DEPLOYMENT, ALStatus.END, m, 0)
        log.debug(m)
        # query virtual machine status
        run_job(MDL_CLS_FUNC[8],
                (self.azure_key_id, ),
                (cloud_service_name, deployment_name, virtual_machine_name, AVMStatus.READY_ROLE,
                 MDL_CLS_FUNC[9], (self.azure_key_id, ), (experiment_id, template_unit)),
                VIRTUAL_MACHINE_TICK)

    # todo make stop_virtual_machine async
    def stop_virtual_machine(self, experiment_id, cloud_service_name, deployment_name, virtual_machine_name, action):
        """
        0. Prerequisites: a. virtual machine exist in both azure and database
                          b. input parameters are correct
        :param experiment_id:
        :param cloud_service_name:
        :param deployment_name:
        :param virtual_machine_name:
        :param action: AVMStatus.STOPPED or AVMStatus.STOPPED_DEALLOCATED
        :return:
        """
        commit_azure_log(experiment_id, ALOperation.STOP_VIRTUAL_MACHINE, ALStatus.START)
        # need_status: AVMStatus.STOPPED_VM or AVMStatus.STOPPED_DEALLOCATED
        need_status = AVMStatus.STOPPED_VM if action == AVMStatus.STOPPED else AVMStatus.STOPPED_DEALLOCATED
        deployment = self.service.get_deployment_by_name(cloud_service_name, deployment_name)
        now_status = self.service.get_virtual_machine_instance_status(deployment, virtual_machine_name)
        if need_status == AVMStatus.STOPPED_VM and now_status == AVMStatus.STOPPED_DEALLOCATED:
            m = self.STOP_VIRTUAL_MACHINE_ERROR[1] % (VIRTUAL_MACHINE,
                                                      virtual_machine_name,
                                                      AVMStatus.STOPPED_VM,
                                                      AVMStatus.STOPPED_DEALLOCATED)
            commit_azure_log(experiment_id, ALOperation.STOP_VIRTUAL_MACHINE, ALStatus.FAIL, m, 1)
            log.error(m)
            return False
        elif need_status == now_status:
            db_status = get_azure_virtual_machine_status(cloud_service_name, deployment_name, virtual_machine_name)
            if db_status == need_status:
                m = self.STOP_VIRTUAL_MACHINE_INFO[1] % (VIRTUAL_MACHINE,
                                                         virtual_machine_name,
                                                         need_status,
                                                         AZURE_FORMATION)
                commit_azure_log(experiment_id, ALOperation.STOP_VIRTUAL_MACHINE, ALStatus.END, m, 1)
            else:
                m = self.STOP_VIRTUAL_MACHINE_INFO[2] % (VIRTUAL_MACHINE,
                                                         virtual_machine_name,
                                                         need_status,
                                                         AZURE_FORMATION)
                self.__stop_virtual_machine_helper(cloud_service_name,
                                                   deployment_name,
                                                   virtual_machine_name,
                                                   need_status)
                commit_azure_log(experiment_id, ALOperation.STOP_VIRTUAL_MACHINE, ALStatus.END, m, 2)
            log.debug(m)
        else:
            try:
                result = self.service.stop_virtual_machine(cloud_service_name,
                                                           deployment_name,
                                                           virtual_machine_name,
                                                           action)
            except Exception as e:
                m = self.STOP_VIRTUAL_MACHINE_ERROR[0] % (VIRTUAL_MACHINE, virtual_machine_name, e.message)
                commit_azure_log(experiment_id, ALOperation.STOP_VIRTUAL_MACHINE, ALStatus.FAIL, 0)
                log.error(e)
                return False
            # make sure async operation succeeds
            if not self.service.wait_for_async(result.request_id, ASYNC_TICK, ASYNC_LOOP):
                m = self.STOP_VIRTUAL_MACHINE_ERROR[2] % (VIRTUAL_MACHINE, virtual_machine_name)
                commit_azure_log(experiment_id, ALOperation.STOP_VIRTUAL_MACHINE, ALStatus.FAIL, 2)
                log.error(m)
                return False
            # make sure role is need status
            if not self.service.wait_for_virtual_machine(cloud_service_name,
                                                         deployment_name,
                                                         virtual_machine_name,
                                                         VIRTUAL_MACHINE_TICK,
                                                         VIRTUAL_MACHINE_LOOP,
                                                         need_status):
                m = self.STOP_VIRTUAL_MACHINE_ERROR[3] % (VIRTUAL_MACHINE, virtual_machine_name)
                commit_azure_log(experiment_id, ALOperation.STOP_VIRTUAL_MACHINE, ALStatus.FAIL, m, 3)
                log.error(m)
                return False
            self.__stop_virtual_machine_helper(cloud_service_name,
                                               deployment_name,
                                               virtual_machine_name,
                                               need_status)
            m = self.STOP_VIRTUAL_MACHINE_INFO[0] % (VIRTUAL_MACHINE, virtual_machine_name, action)
            commit_azure_log(experiment_id, ALOperation.STOP_VIRTUAL_MACHINE, ALStatus.END, m, 0)
            log.debug(m)
        return True

    # todo make start_virtual_machine async
    def start_virtual_machine(self, experiment_id, cloud_service_name, deployment_name, virtual_machine_name):
        """
        0. Prerequisites: a. virtual machine exist in both azure and database
                          b. input parameters are correct
        :param experiment_id:
        :param cloud_service_name:
        :param deployment_name:
        :param virtual_machine_name:
        :return:
        """
        commit_azure_log(experiment_id, ALOperation.START_VIRTUAL_MACHINE, ALStatus.START)
        deployment = self.service.get_deployment_by_name(cloud_service_name, deployment_name)
        status = self.service.get_virtual_machine_instance_status(deployment, virtual_machine_name)
        if status == AVMStatus.READY_ROLE:
            db_status = get_azure_virtual_machine_status(cloud_service_name, deployment_name, virtual_machine_name)
            if db_status == status:
                m = self.START_VIRTUAL_MACHINE_INFO[1] % (VIRTUAL_MACHINE, virtual_machine_name, AZURE_FORMATION)
                commit_azure_log(experiment_id, ALOperation.START_VIRTUAL_MACHINE, ALStatus.END, m, 1)
            else:
                m = self.START_VIRTUAL_MACHINE_INFO[2] % (VIRTUAL_MACHINE, virtual_machine_name, AZURE_FORMATION)
                self.__start_virtual_machine_helper(cloud_service_name, deployment_name, virtual_machine_name)
                commit_azure_log(experiment_id, ALOperation.START_VIRTUAL_MACHINE, ALStatus.END, m, 2)
            log.debug(m)
        else:
            try:
                result = self.service.start_virtual_machine(cloud_service_name,
                                                            deployment_name,
                                                            virtual_machine_name)
            except Exception as e:
                m = self.START_VIRTUAL_MACHINE_ERROR[0] % (VIRTUAL_MACHINE, virtual_machine_name, e.message)
                commit_azure_log(experiment_id, ALOperation.START_VIRTUAL_MACHINE, ALStatus.FAIL, 0)
                log.error(e)
                return False
            # make sure async operation succeeds
            if not self.service.wait_for_async(result.request_id, ASYNC_TICK, ASYNC_LOOP):
                m = self.START_VIRTUAL_MACHINE_ERROR[1] % (VIRTUAL_MACHINE, virtual_machine_name)
                commit_azure_log(experiment_id, ALOperation.START_VIRTUAL_MACHINE, ALStatus.FAIL, 1)
                log.error(m)
                return False
            # make sure role is need status
            if not self.service.wait_for_virtual_machine(cloud_service_name,
                                                         deployment_name,
                                                         virtual_machine_name,
                                                         VIRTUAL_MACHINE_TICK,
                                                         VIRTUAL_MACHINE_LOOP,
                                                         AVMStatus.READY_ROLE):
                m = self.START_VIRTUAL_MACHINE_ERROR[2] % (VIRTUAL_MACHINE, virtual_machine_name)
                commit_azure_log(experiment_id, ALOperation.START_VIRTUAL_MACHINE, ALStatus.FAIL, m, 2)
                log.error(m)
                return False
            self.__start_virtual_machine_helper(cloud_service_name, deployment_name, virtual_machine_name)
            m = self.START_VIRTUAL_MACHINE_INFO[0] % (VIRTUAL_MACHINE, virtual_machine_name)
            commit_azure_log(experiment_id, ALOperation.START_VIRTUAL_MACHINE, ALStatus.END, m, 0)
        return True

    # todo delete virtual machine
    def delete_virtual_machine(self):
        raise NotImplementedError

    # --------------------------------------------- helper function ---------------------------------------------#

    def __create_virtual_machine_helper(self, experiment_id, template_unit):
        cloud_service_name = template_unit.get_cloud_service_name()
        deployment_slot = template_unit.get_deployment_slot()
        deployment_name = self.service.get_deployment_name(cloud_service_name, deployment_slot)
        virtual_machine_name = self.VIRTUAL_MACHINE_NAME_BASE % (template_unit.get_virtual_machine_name(),
                                                                 experiment_id)
        public_ip = self.service.get_virtual_machine_public_ip(cloud_service_name,
                                                               deployment_name,
                                                               virtual_machine_name)
        remote_port_name = template_unit.get_remote_port_name()
        remote_port = self.service.get_virtual_machine_public_endpoint(cloud_service_name,
                                                                       deployment_name,
                                                                       virtual_machine_name,
                                                                       remote_port_name)
        remote_paras = template_unit.get_remote_paras(virtual_machine_name,
                                                      public_ip,
                                                      remote_port)
        virtual_environment = commit_virtual_environment(VEProvider.AzureVM,
                                                         template_unit.get_remote_provider_name(),
                                                         template_unit.get_image_name(),
                                                         VEStatus.Running,
                                                         VERemoteProvider.Guacamole,
                                                         json.dumps(remote_paras),
                                                         experiment_id)
        dns = self.service.get_deployment_dns(cloud_service_name, deployment_slot)
        private_ip = self.service.get_virtual_machine_private_ip(cloud_service_name,
                                                                 deployment_name,
                                                                 virtual_machine_name)
        virtual_machine_label = template_unit.get_virtual_machine_label()
        virtual_machine = commit_azure_virtual_machine(virtual_machine_name,
                                                       virtual_machine_label,
                                                       AVMStatus.READY_ROLE,
                                                       dns,
                                                       public_ip,
                                                       private_ip,
                                                       cloud_service_name,
                                                       deployment_name,
                                                       experiment_id,
                                                       virtual_environment)
        network_config = self.service.get_virtual_machine_network_config(cloud_service_name,
                                                                         deployment_name,
                                                                         virtual_machine_name)
        for input_endpoint in network_config.input_endpoints.input_endpoints:
            commit_azure_endpoint(input_endpoint.name,
                                  input_endpoint.protocol,
                                  input_endpoint.port,
                                  input_endpoint.local_port,
                                  virtual_machine)
        m = self.CREATE_VIRTUAL_MACHINE_INFO[0] % (VIRTUAL_MACHINE, virtual_machine_name)
        commit_azure_log(experiment_id, ALOperation.CREATE_VIRTUAL_MACHINE, ALStatus.END, m, 0)
        log.debug(m)

    def __stop_virtual_machine_helper(self,
                                      cloud_service_name,
                                      deployment_name,
                                      virtual_machine_name,
                                      need_status):
        """
        Update status of azure virtual machine and virtual environment
        :param cloud_service_name:
        :param deployment_name:
        :param virtual_machine_name:
        :param need_status:
        :return:
        """
        virtual_machine = update_azure_virtual_machine_status(cloud_service_name,
                                                              deployment_name,
                                                              virtual_machine_name,
                                                              need_status)
        update_virtual_environment_status(virtual_machine, VEStatus.Stopped)

    def __start_virtual_machine_helper(self,
                                       cloud_service_name,
                                       deployment_name,
                                       virtual_machine_name):
        """
        Update status of azure virtual machine and virtual environment
        Update private ip of azure virtual machine
        :param cloud_service_name:
        :param deployment_name:
        :param virtual_machine_name:
        :return:
        """
        virtual_machine = update_azure_virtual_machine_status(cloud_service_name,
                                                              deployment_name,
                                                              virtual_machine_name,
                                                              AVMStatus.READY_ROLE)
        update_virtual_environment_status(virtual_machine, VEStatus.Running)
        private_ip = self.service.get_virtual_machine_private_ip(cloud_service_name,
                                                                 deployment_name,
                                                                 virtual_machine_name)
        update_virtual_environment_private_ip(virtual_machine, private_ip)