__author__ = 'Yifu Huang'

from src.app.cloudABC import CloudABC
from src.app.database import *
from src.app.log import *
from azure.servicemanagement import *
import json
import time
import os
import commands
import datetime


class AzureImpl(CloudABC):
    """
    Azure cloud service management
    For logic: manage only resources created by this program itself
    For template: one storage account, one container, one cloud service, one deployment,
    multiple virtual machines (Windows/Linux), multiple input endpoints
    """

    def __init__(self):
        super(AzureImpl, self).__init__()
        self.sms = None
        self.user_template = None
        self.template_config = None
        self.update_template_config = None

    def register(self, name, email, subscription_id, management_host):
        """
        Create user info and key according to given information:
        1. Create user info
        2. Create cer and pem file
        :param name:
        :param email:
        :param subscription_id:
        :param management_host:
        :return: user info
        """
        user_info = super(AzureImpl, self).register(name, email)
        certificates_dir = os.path.dirname(__file__) + os.path.sep + 'certificates'
        # make sure certificate dir exists
        if not os.path.isdir(certificates_dir):
            os.mkdir(certificates_dir)
        base_url = '%s/%s-%s' % (certificates_dir, user_info.id, subscription_id)
        pem_url = base_url + '.pem'
        # avoid duplicate pem generation
        if not os.path.isfile(pem_url):
            pem_command = 'openssl req -x509 -nodes -days 365 -newkey rsa:1024 -keyout %s -out %s -batch' %\
                          (pem_url, pem_url)
            commands.getstatusoutput(pem_command)
        else:
            log.debug('%s exist' % pem_url)
        cert_url = base_url + '.cer'
        # avoid duplicate cer generation
        if not os.path.isfile(cert_url):
            cert_command = 'openssl x509 -inform pem -in %s -outform der -out %s' % (pem_url, cert_url)
            commands.getstatusoutput(cert_command)
        else:
            log.debug('%s exist' % cert_url)
        # avoid duplicate user key
        user_key = UserKey.query.filter_by(user_info=user_info).first()
        if user_key is None:
            user_key = UserKey(user_info, cert_url, pem_url, subscription_id, management_host)
            db.session.add(user_key)
            db.session.commit()
        else:
            log.debug('user key [%d] has registered' % user_key.id)
        return user_info

    def connect(self, user_info):
        """
        Connect to azure service management service according to given user info
        :param user_info:
        :return: Whether service management service is connected
        """
        user_key = UserKey.query.filter_by(user_info=user_info).first()
        # make sure user key exists
        if user_key is None:
            log.debug('user [%d] not exist' % user_info.id)
            return False
        try:
            self.sms = ServiceManagementService(user_key.subscription_id, user_key.pem_url, user_key.management_host)
        except Exception as e:
            log.debug(e)
            return False
        return True

    def create(self, user_template):
        """
        Create virtual machines according to given user template (assume all fields needed are in template)
        1. Load template from json into dictionary
        2. If storage account not exist, then create it
        3. If cloud service not exist, then create it
        4. If deployment not exist, then create virtual machine with deployment
           Else add virtual machine to deployment
        :param user_template:
        :return: Whether a virtual machines are created
        """
        if not self._load_template(user_template):
            return False
        if not self._create_storage_account():
            return False
        if not self._create_cloud_service():
            return False
        if not self._create_virtual_machines():
            return False
        return True

    def update(self, user_template, update_template):
        """
        Update virtual machines created by user template according to given update template
        (assume all fields needed are in template, resources in user template and update template are the same)
        Currently support only network config and role size
        :param user_template:
        :param update_template:
        :return: Whether virtual machines are updated
        """
        if not self._load_template(user_template):
            return False
        if not self._load_update_template(update_template):
            return False
        self._user_operation_commit('update', 'start')
        cloud_service = self.template_config['cloud_service']
        deployment = self.template_config['deployment']
        virtual_machines = self.template_config['virtual_machines']
        cs = UserResource.query.filter_by(user_template=self.user_template,
                                          type='cloud service',
                                          name=cloud_service['service_name'],
                                          status='Running').first()
        # make sure cloud service exist in database
        if cs is None:
            m = 'cloud service %s not exist in database' % cloud_service['service_name']
            self._user_operation_commit('update', 'fail', m)
            log.debug(m)
            return False
        # make sure cloud service exist in azure
        if not self._hosted_service_exists(cloud_service['service_name']):
            m = 'cloud service %s not exist in azure' % cloud_service['service_name']
            self._user_operation_commit('update', 'fail', m)
            log.debug(m)
            return False
        # make sure deployment exist in database
        if UserResource.query.filter_by(user_template=self.user_template,
                                        type='deployment',
                                        name=deployment['deployment_name'],
                                        status='Running',
                                        cloud_service_id=cs.id).count() == 0:
            m = 'deployment %s not exist in database' % deployment['deployment_name']
            self._user_operation_commit('update', 'fail', m)
            log.debug(m)
            return False
        # make sure deployment exist in azure
        if not self._deployment_exists(cloud_service['service_name'], deployment['deployment_name']):
            m = 'deployment %s not exist in azure' % deployment['deployment_name']
            self._user_operation_commit('update', 'fail', m)
            log.debug(m)
            return False
        for virtual_machine in virtual_machines:
            # make sure virtual machine exist in database
            if UserResource.query.filter_by(user_template=self.user_template,
                                            type='virtual machine',
                                            name=virtual_machine['role_name'],
                                            status='Running',
                                            cloud_service_id=cs.id).count() == 0:
                m = 'virtual machine %s not exist in database' % virtual_machine['role_name']
                self._user_operation_commit('update', 'fail', m)
                log.debug(m)
                return False
            # make sure virtual machine exist in azure
            if not self._role_exists(cloud_service['service_name'], deployment['deployment_name'],
                                     virtual_machine['role_name']):
                m = 'virtual machine %s not exist in azure' % virtual_machine['role_name']
                self._user_operation_commit('update', 'fail', m)
                log.debug(m)
                return False
        # now check done, begin update
        update_virtual_machines = self.update_template_config['virtual_machines']
        for update_virtual_machine in update_virtual_machines:
            self._user_operation_commit('update_virtual_machine', 'start')
            network_config = update_virtual_machine['network_config']
            network = ConfigurationSet()
            network.configuration_set_type = network_config['configuration_set_type']
            input_endpoints = network_config['input_endpoints']
            vm = UserResource.query.filter_by(user_template=self.user_template, type='virtual machine',
                                              name=update_virtual_machine['role_name'], status='Running',
                                              cloud_service_id=cs.id).first()
            old_endpoints = VMEndpoint.query.filter_by(virtual_machine=vm).all()
            new_endpoints = []
            for input_endpoint in input_endpoints:
                endpoint = VMEndpoint(input_endpoint['name'], input_endpoint['protocol'],
                                      input_endpoint['port'], input_endpoint['local_port'], cs, vm)
                new_endpoints.append(endpoint)
                network.input_endpoints.input_endpoints.append(
                    ConfigurationSetInputEndpoint(input_endpoint['name'], input_endpoint['protocol'],
                                                  input_endpoint['port'], input_endpoint['local_port']))
            try:
                result = self.sms.update_role(cloud_service['service_name'], deployment['deployment_name'],
                                              update_virtual_machine['role_name'], network_config=network,
                                              role_size=update_virtual_machine['role_size'])
            except Exception as e:
                self._user_operation_commit('update_virtual_machine', 'fail', e.message)
                log.debug(e)
                return False
            # make sure async operation succeeds
            if not self._wait_for_async(result.request_id, 30, 60):
                m = '_wait_for_async fail'
                self._user_operation_commit('update_virtual_machine', 'fail', m)
                log.debug(m)
                return False
            # make sure role is ready
            if not self._wait_for_role(cloud_service['service_name'], deployment['deployment_name'],
                                       update_virtual_machine['role_name'], 30, 60):
                m = 'virtual machine %s updated but not ready' % update_virtual_machine['role_name']
                self._user_operation_commit('update_virtual_machine', 'fail', m)
                log.debug(m)
                return False
            role = self.sms.get_role(cloud_service['service_name'], deployment['deployment_name'],
                                     update_virtual_machine['role_name'])
            # make sure virtual machine is updated
            if role.role_size != update_virtual_machine['role_size'] or not self._cmp_network_config(
                    role.configuration_sets, network):
                m = 'virtual machine %s updated but failed' % update_virtual_machine['role_name']
                self._user_operation_commit('update_virtual_machine', 'fail', m)
                log.debug(m)
                return False
            for old_endpoint in old_endpoints:
                db.session.delete(old_endpoint)
            for new_endpoint in new_endpoints:
                db.session.add(new_endpoint)
            db.session.commit()
            self._user_operation_commit('update_virtual_machine', 'end')
        self._user_operation_commit('update', 'end')
        self.update_template_config = None
        return True

    def delete(self, user_template):
        """
        Delete a virtual machine according to given user template (assume all fields needed are in template)
        If deployment has only a virtual machine, then delete a virtual machine with deployment
        Else delete a virtual machine from deployment
        :param user_template:
        :return: Whether a virtual machine is deleted
        """
        if not self._load_template(user_template):
            return False
        self._user_operation_commit('delete', 'start')
        cloud_service = self.template_config['cloud_service']
        deployment = self.template_config['deployment']
        virtual_machines = self.template_config['virtual_machines']
        # make sure cloud service exist in database
        cs = UserResource.query.filter_by(user_template=self.user_template, type='cloud service',
                                          name=cloud_service['service_name'], status='Running').first()
        if cs is None:
            m = 'cloud service %s not exist in database' % cloud_service['service_name']
            self._user_operation_commit('delete', 'fail', m)
            log.debug(m)
            return False
        # make sure cloud service exist in azure
        if not self._hosted_service_exists(cloud_service['service_name']):
            m = 'cloud service %s not exist in azure' % cloud_service['service_name']
            self._user_operation_commit('delete', 'fail', m)
            log.debug(m)
            return False
        # make sure deployment exist in database
        if UserResource.query.filter_by(user_template=self.user_template,
                                        type='deployment',
                                        name=deployment['deployment_name'],
                                        status='Running', cloud_service_id=cs.id).count() == 0:
            m = 'deployment %s not exist in database' % deployment['deployment_name']
            self._user_operation_commit('delete', 'fail', m)
            log.debug(m)
            return False
        # make sure deployment exist in azure
        if not self._deployment_exists(cloud_service['service_name'], deployment['deployment_name']):
            m = 'deployment %s not exist in azure' % deployment['deployment_name']
            self._user_operation_commit('delete', 'fail', m)
            log.debug(m)
            return False
        for virtual_machine in virtual_machines:
            # make sure virtual machine exist in database
            if UserResource.query.filter_by(user_template=self.user_template,
                                            type='virtual machine',
                                            name=virtual_machine['role_name'],
                                            status='Running', cloud_service_id=cs.id).count() == 0:
                m = 'virtual machine %s not exist in database' % virtual_machine['role_name']
                self._user_operation_commit('delete', 'fail', m)
                log.debug(m)
                return False
            # make sure virtual machine exist in azure
            if not self._role_exists(cloud_service['service_name'], deployment['deployment_name'],
                                     virtual_machine['role_name']):
                m = 'virtual machine %s not exist in azure' % virtual_machine['role_name']
                self._user_operation_commit('delete', 'fail', m)
                log.debug(m)
                return False
        for virtual_machine in virtual_machines:
            deploy = self.sms.get_deployment_by_name(cloud_service['service_name'], deployment['deployment_name'])
            # whether only one virtual machine in deployment
            if len(deploy.role_instance_list) == 1:
                self._user_operation_commit('delete_deployment', 'start')
                self._user_operation_commit('delete_virtual_machine', 'start')
                try:
                    result = self.sms.delete_deployment(cloud_service['service_name'], deployment['deployment_name'])
                except Exception as e:
                    self._user_operation_commit('delete_deployment', 'fail', e.message)
                    self._user_operation_commit('delete_virtual_machine', 'fail', e.message)
                    log.debug(e)
                    return False
                # make sure async operation succeeds
                if not self._wait_for_async(result.request_id, 30, 60):
                    m = '_wait_for_async fail'
                    self._user_operation_commit('delete_deployment', 'fail', m)
                    self._user_operation_commit('delete_virtual_machine', 'fail', m)
                    log.debug(m)
                    return False
                # make sure deployment not exist
                if self._deployment_exists(cloud_service['service_name'], deployment['deployment_name']):
                    m = 'deployment %s deleted but failed' % deployment['deployment_name']
                    self._user_operation_commit('delete_deployment', 'fail', m)
                    log.debug(m)
                    return False
                else:
                    dm = UserResource.query.filter_by(user_template=user_template, type='deployment',
                                                      name=deployment['deployment_name'], status='Running',
                                                      cloud_service_id=cs.id).first()
                    dm.status = 'Deleted'
                    db.session.commit()
                    self._user_operation_commit('delete_deployment', 'end')
                # make sure virtual machine not exist
                if self._role_exists(cloud_service['service_name'], deployment['deployment_name'],
                                     virtual_machine['role_name']):
                    m = 'virtual machine %s deleted but failed' % virtual_machine['role_name']
                    self._user_operation_commit('delete_virtual_machine', 'fail', m)
                    log.debug(m)
                    return False
                else:
                    vm = UserResource.query.filter_by(user_template=user_template, type='virtual machine',
                                                      name=virtual_machine['role_name'], status='Running',
                                                      cloud_service_id=cs.id).first()
                    VMEndpoint.query.filter_by(virtual_machine=vm).delete()
                    VMConfig.query.filter_by(virtual_machine=vm).delete()
                    vm.status = 'Deleted'
                    db.session.commit()
                    self._user_operation_commit('delete_virtual_machine', 'end')
            else:
                self._user_operation_commit('delete_virtual_machine', 'start')
                try:
                    result = self.sms.delete_role(cloud_service['service_name'], deployment['deployment_name'],
                                                  virtual_machine['role_name'])
                except Exception as e:
                    self._user_operation_commit('delete_virtual_machine', 'fail', e.message)
                    log.debug(e)
                    return False
                # make sure async operation succeeds
                if not self._wait_for_async(result.request_id, 30, 60):
                    m = '_wait_for_async fail'
                    self._user_operation_commit('delete_virtual_machine', 'fail', m)
                    log.debug(m)
                    return False
                # make sure virtual machine not exist
                if self._role_exists(cloud_service['service_name'], deployment['deployment_name'],
                                     virtual_machine['role_name']):
                    m = 'virtual machine %s deleted but failed' % virtual_machine['role_name']
                    self._user_operation_commit('delete_virtual_machine', 'fail', m)
                    log.debug(m)
                    return False
                else:
                    vm = UserResource.query.filter_by(user_template=user_template, type='virtual machine',
                                                      name=virtual_machine['role_name'], status='Running',
                                                      cloud_service_id=cs.id).first()
                    VMEndpoint.query.filter_by(virtual_machine=vm).delete()
                    VMConfig.query.filter_by(virtual_machine=vm).delete()
                    vm.status = 'Deleted'
                    db.session.commit()
                    self._user_operation_commit('delete_virtual_machine', 'end')
        self._user_operation_commit('delete', 'end')
        return True

    # --------------------------------------------helper function-------------------------------------------- #

    def _load_template(self, user_template):
        """
        Load json based template into dictionary
        :param user_template:
        :return:
        """
        self.user_template = user_template
        # make sure template url exists
        if os.path.isfile(user_template.template.url):
            try:
                self.template_config = json.load(file(user_template.template.url))
            except Exception as e:
                log.debug('ugly json format: %s' % e)
                return False
        else:
            log.debug('%s not exist' % user_template.template.url)
            return False
        return True

    def _deployment_exists(self, service_name, deployment_name):
        """
        Check whether specific deployment exist
        :param service_name:
        :param deployment_name:
        :return:
        """
        try:
            props = self.sms.get_deployment_by_name(service_name, deployment_name)
        except Exception as e:
            if e.message != 'Not found (Not Found)':
                log.debug('deployment %s: %s' % (deployment_name, e))
            return False
        return props is not None

    def _vm_endpoint_rollback(self, cs):
        """
        Rollback vm endpoint in database because no vm created
        :param cs:
        :return:
        """
        VMEndpoint.query.filter_by(cloud_service=cs, virtual_machine=None).delete()
        db.session.commit()

    def _role_exists(self, service_name, deployment_name, role_name):
        """
        Check whether specific virtual machine exist
        :param service_name:
        :param deployment_name:
        :param role_name:
        :return:
        """
        try:
            props = self.sms.get_role(service_name, deployment_name, role_name)
        except Exception as e:
            if e.message != 'Not found (Not Found)':
                log.debug('virtual machine %s: %s' % (role_name, e))
            return False
        return props is not None

    def _vm_endpoint_update(self, cs, vm):
        """
        Update vm endpoint in database after vm created
        :param cs:
        :param vm:
        :return:
        """
        vm_endpoints = VMEndpoint.query.filter_by(cloud_service=cs, virtual_machine=None).all()
        for vm_endpoint in vm_endpoints:
            vm_endpoint.virtual_machine = vm
        db.session.commit()

    def _vm_config_commit(self, vm, dns, public_ip, private_ip):
        """
        Commit vm config to database
        :param vm:
        :return:
        """
        vm_config = VMConfig(vm, dns, public_ip, private_ip)
        db.session.add(vm_config)
        db.session.commit()

    def _wait_for_deployment(self, service_name, deployment_name, second_per_loop, loop, status='Running'):
        """
        Wait for deployment until running, up to second_per_loop * loop
        :param service_name:
        :param deployment_name:
        :param second_per_loop:
        :param loop:
        :param status:
        :return:
        """
        count = 0
        props = self.sms.get_deployment_by_name(service_name, deployment_name)
        while props.status != status:
            log.debug('_wait_for_deployment [%s] loop count: %d' % (deployment_name, count))
            count += 1
            if count > loop:
                log.debug('Timed out waiting for deployment status.')
                return False
            time.sleep(second_per_loop)
            props = self.sms.get_deployment_by_name(service_name, deployment_name)
        return props.status == status

    def _wait_for_role(self, service_name, deployment_name, role_instance_name,
                       second_per_loop, loop, status='ReadyRole'):
        """
        Wait virtual machine until ready, up to second_per_loop * loop
        :param service_name:
        :param deployment_name:
        :param role_instance_name:
        :param second_per_loop:
        :param loop:
        :param status:
        :return:
        """
        count = 0
        props = self.sms.get_deployment_by_name(service_name, deployment_name)
        while self._get_role_instance_status(props, role_instance_name) != status:
            log.debug('_wait_for_role [%s] loop count: %d' % (role_instance_name, count))
            count += 1
            if count > loop:
                log.debug('Timed out waiting for role instance status.')
                return False
            time.sleep(second_per_loop)
            props = self.sms.get_deployment_by_name(service_name, deployment_name)
        return self._get_role_instance_status(props, role_instance_name) == status

    def _get_role_instance_status(self, deployment, role_instance_name):
        """
        Get virtual machine status
        :param deployment:
        :param role_instance_name:
        :return:
        """
        for role_instance in deployment.role_instance_list:
            if role_instance.instance_name == role_instance_name:
                return role_instance.instance_status
        return None

    def _load_update_template(self, update_template):
        """
        Load json based template into dictionary
        :param update_template:
        :return:
        """
        # make sure template url exists
        if os.path.isfile(update_template.template.url):
            try:
                self.update_template_config = json.load(file(update_template.template.url))
            except Exception as e:
                log.debug('ugly json format: %s' % e)
                return False
        else:
            log.debug('%s not exist' % update_template.template.url)
            return False
        return True

    def _cmp_network_config(self, configuration_sets, network2):
        """
        Check whether two network config are the same
        :param configuration_sets:
        :param network2:
        :return:
        """
        for network1 in configuration_sets:
            if network1.configuration_set_type == 'NetworkConfiguration':
                points1 = network1.input_endpoints.input_endpoints
                points1 = sorted(points1, key=lambda point: point.name)
                points2 = network2.input_endpoints.input_endpoints
                points2 = sorted(points2, key=lambda point: point.name)
                if len(points1) != len(points2):
                    return False
                for i in range(len(points1)):
                    if points1[i].name != points2[i].name:
                        return False
                    if points1[i].protocol != points2[i].protocol:
                        return False
                    if points1[i].port != points2[i].port:
                        return False
                    if points1[i].local_port != points2[i].local_port:
                        return False
                return True
        return False