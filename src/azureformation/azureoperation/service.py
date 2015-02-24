__author__ = 'Yifu Huang'


from src.azureformation.azureoperation.utility import (
    NOT_FOUND,
    NETWORK_CONFIGURATION
)
from src.azureformation.log import (
    log
)
from azure.servicemanagement import (
    ServiceManagementService
)


class Service(ServiceManagementService):
    """
    Wrapper of azure service management service
    """

    def __init__(self, subscription_id, pem_url, management_host):
        super(Service, self).__init__(subscription_id, pem_url, management_host)

    # ---------------------------------------- subscription ---------------------------------------- #

    def get_subscription(self):
        return super(Service, self).get_subscription()

    # ---------------------------------------- storage account ---------------------------------------- #

    def get_storage_account_properties(self, name):
        return super(Service, self).get_storage_account_properties(name)

    def storage_account_exists(self, name):
        """
        Check whether specific storage account exist in specific azure subscription
        :param name:
        :return:
        """
        try:
            props = self.get_storage_account_properties(name)
        except Exception as e:
            if e.message != NOT_FOUND:
                log.error(e)
            return False
        return props is not None

    def check_storage_account_name_availability(self, name):
        return super(Service, self).check_storage_account_name_availability(name)

    def create_storage_account(self, name, description, label, location):
        return super(Service, self).create_storage_account(name, description, label, location=location)

    # ---------------------------------------- cloud service ---------------------------------------- #

    def get_hosted_service_properties(self, name, detail=False):
        return super(Service, self).get_hosted_service_properties(name, detail)

    def cloud_service_exists(self, name):
        """
        Check whether specific cloud service exist in specific azure subscription
        :param name:
        :return:
        """
        try:
            props = self.get_hosted_service_properties(name)
        except Exception as e:
            if e.message != NOT_FOUND:
                log.error(e)
            return False
        return props is not None

    def check_hosted_service_name_availability(self, name):
        return super(Service, self).check_hosted_service_name_availability(name)

    def create_hosted_service(self, name, label, location):
        return super(Service, self).create_hosted_service(name, label, location=location)

    # ---------------------------------------- deployment ---------------------------------------- #

    def get_deployment_by_slot(self, service_name, deployment_slot):
        return super(Service, self).get_deployment_by_slot(service_name, deployment_slot)

    def deployment_exists(self, service_name, deployment_slot):
        """
        Check whether specific deployment slot exist in specific azure subscription
        :param service_name:
        :param deployment_slot:
        :return:
        """
        try:
            props = self.get_deployment_by_slot(service_name, deployment_slot)
        except Exception as e:
            if e.message != NOT_FOUND:
                log.error(e)
            return False
        return props is not None

    # ---------------------------------------- virtual machine ---------------------------------------- #

    def get_role(self, service_name, deployment_name, role_name):
        return super(Service, self).get_role(service_name, deployment_name, role_name)

    def role_exists(self, service_name, deployment_name, role_name):
        """
        Check whether specific virtual machine exist in specific azure subscription
        :param service_name:
        :param deployment_name:
        :param role_name:
        :return:
        """
        try:
            props = self.get_role(service_name, deployment_name, role_name)
        except Exception as e:
            if e.message != NOT_FOUND:
                log.error(e)
            return False
        return props is not None

    # ---------------------------------------- endpoint ---------------------------------------- #

    def get_assigned_endpoints(self, cloud_service_name):
        properties = self.get_hosted_service_properties(cloud_service_name, True)
        endpoints = []
        for deployment in properties.deployments.deployments:
            for role in deployment.role_list.roles:
                for configuration_set in role.configuration_sets.configuration_sets:
                    if configuration_set.configuration_set_type == NETWORK_CONFIGURATION:
                        if configuration_set.input_endpoints is not None:
                            for input_endpoint in configuration_set.input_endpoints.input_endpoints:
                                endpoints.append(input_endpoint.port)
        return endpoints

    # ---------------------------------------- other ---------------------------------------- #

    def get_operation_status(self, request_id):
        return super(Service, self).get_operation_status(request_id)