# coding=utf-8
"""OpenStack based CSP"""

import keystoneauth1.exceptions.http as _keystoneauth_exceptions
import openstack as _openstack

from acceleratorAPI.csp import CSPGenericClass as _CSPGenericClass
import acceleratorAPI.configuration as _cfg
import acceleratorAPI.exceptions as _exc
import acceleratorAPI._utilities as _utl
from acceleratorAPI._utilities import get_logger as _get_logger


class OpenStackClass(_CSPGenericClass):
    """Generic class for OpenStack based CSP

    Args:
        provider (str): Cloud service provider name.
        config (str or acceleratorAPI.configuration.Configuration): Configuration file path or instance.
            If not set, will search it in current working directory, in current
            user "home" folder. If none found, will use default configuration values.
        client_id (str): OpenStack Access Key ID.
        secret_id (str): OpenStack Secret Access Key.
        region (str): OpenStack region. Needs a region supporting instances with FPGA devices.
        instance_type (str): OpenStack Flavor. Default defined by accelerator.
        ssh_key (str): OpenStack Key pair. Default to 'MySSHKey'.
        security_group: OpenStack Security group. Default to 'MySecurityGroup'.
        instance_id (str): Instance ID of an already existing OpenStack nova instance to use.
            If not specified, create a new instance.
        instance_url (str): IP address of an already existing OpenStack nova instance to use.
            If not specified, create a new instance.
        project_id (str): OpenStack Project
        auth_url (str): OpenStack auth-URL
        interface (str): OpenStack interface (default to 'public')
        stop_mode (str or int): Define the "stop_instance" method behavior. Default to 'term'.
            See "stop_mode" property for more information and possible values.
        exit_instance_on_signal (bool): If True, exit instance
            on OS exit signals. This may help to not have instance still running
            if Python interpreter is not exited properly. Note: this is provided for
            convenience and does not cover all exit case like process kill and
            may not work on all OS.
    """

    #: Default OpenStack auth-URL to use (str)
    OPENSTACK_AUTH_URL = None

    #: Default Interface to use (str)
    OPENSTACK_INTERFACE = 'public'

    _INFO_NAMES = _CSPGenericClass._INFO_NAMES.copy()
    _INFO_NAMES.update({'_project_id', '_auth_url', '_interface'})

    def __init__(self, config=None, project_id=None, auth_url=None, interface=None, **kwargs):
        config = _cfg.create_configuration(config)
        _CSPGenericClass.__init__(self, config=config, **kwargs)

        # OpenStack specific arguments
        self._project_id = config.get_default(
            'csp', 'project_id', overwrite=project_id)
        self._auth_url = config.get_default(
            'csp', 'auth_url', overwrite=auth_url, default=self.OPENSTACK_AUTH_URL)
        self._interface = config.get_default(
            'csp', 'interface', overwrite=interface, default=self.OPENSTACK_INTERFACE)

        # Checks mandatory configuration values
        self._check_arguments('project_id', 'auth_url', 'interface')

        # Load session
        self._session = _openstack.connection.Connection(
            region_name=self._region,
            auth=dict(
                auth_url=self._auth_url,
                username=self._client_id,
                password=self._secret_id,
                project_id=self._project_id
            ),
            compute_api_version='2',
            identity_interface=self._interface
        )

    def _check_credential(self):
        """
        Check CSP credentials.

        Raises:
            acceleratorAPI.exceptions.CSPAuthenticationException:
                Authentication failed.
        """
        try:
            list(self._session.network.networks())
        except _keystoneauth_exceptions.Unauthorized:
            raise _exc.CSPAuthenticationException()

    def _init_ssh_key(self):
        """
        Initialize SSH key.

        Returns:
            bool: True if reuse existing key
        """
        # Get key pair from CSP
        key_pair = self._session.compute.find_keypair(self._ssh_key, ignore_missing=True)

        # Use existing key
        if key_pair:
            return True

        # Create key pair if not exists
        key_pair = self._session.compute.create_keypair(name=self._ssh_key)

        _utl.create_ssh_key_file(self._ssh_key, key_pair.private_key)

        return False

    def _init_security_group(self):
        """
        Initialize CSP security group.
        """
        # Create security group if not exists
        security_group = self._session.get_security_group(self._security_group)
        if security_group is None:
            security_group = self._session.create_security_group(
                self._security_group, "Generated by accelize API", project_id=self._project_id)
            _get_logger().info("Created security group with ID %s", security_group.name)

        # Verify rules associated to security group for host IP address
        public_ip = _utl.get_host_public_ip()

        # Create rule on SSH
        try:
            self._session.create_security_group_rule(
                security_group.id, port_range_min=22, port_range_max=22, protocol="tcp", remote_ip_prefix=public_ip,
                project_id=self._project_id)

        except _openstack.exceptions.SDKException:
            pass

        # Create rule on HTTP
        try:
            self._session.create_security_group_rule(
                security_group.id, port_range_min=80, port_range_max=80, protocol="tcp", remote_ip_prefix=public_ip,
                project_id=self._project_id)
        except _openstack.exceptions.SDKException:
            pass

        _get_logger().info("Added in security group '%s': SSH and HTTP for IP %s.",
                           self._security_group, public_ip)

    def _get_instance(self):
        """
        Returns current instance.

        Returns:
            object: Instance
        """
        # Try to find instance
        try:
            return self._session.get_server(self._instance_id)

        # Instance not found
        except _openstack.exceptions.SDKException as exception:
            raise _exc.CSPInstanceException(
                "Could not find an instance with ID '%s'", self._instance_id, exc=exception)

    def _get_instance_public_ip(self):
        """
        Read current instance public IP from CSP instance.

        Returns:
            str: IP address
        """
        for address in self._instance.addresses.values()[0]:
            if address['version'] == 4:
                return address['addr']
        raise _exc.CSPInstanceException("No instance address found")

    def _get_instance_private_ip(self):
        """
        Read current instance private IP from CSP instance.

        Returns:
            str: IP address
        """
        return ''

    def _get_instance_status(self):
        """
        Returns current status of current instance.

        Returns:
            str: Status
        """
        return self._instance.status

    def _create_instance(self):
        """
        Initialize and create instance.
        """
        self._init_security_group()

    def _get_image_id_from_region(self, accel_parameters_in_region):
        """
        Read accelerator parameters and get image id.

        Args:
            accel_parameters_in_region (dict): AcceleratorClient parameters
                for the current CSP region.

        Returns:
            str: image_id
        """
        # Gets image
        image_id = _CSPGenericClass._get_image_id_from_region(
            self, accel_parameters_in_region)

        # Checks if image exists and get its name
        try:
            image = self._session.compute.find_image(image_id)
        except _openstack.exceptions.ResourceNotFound:
            raise _exc.CSPConfigurationException(
                ("Failed to get image information for CSP '%s':\n"
                 "The image '%s' is not available on your CSP account. "
                 "Please contact Accelize.") %
                (self._provider, image_id))
        else:
            self._image_name = image.name

        return image_id

    def _get_instance_type_from_region(self, accel_parameters_in_region):
        """
        Read accelerator parameters and instance type.

        Args:
            accel_parameters_in_region (dict): AcceleratorClient parameters
                for the current CSP region.

        Returns:
            str: instance_type
        """
        # Get instance type (flavor)
        self._instance_type_name = _CSPGenericClass._get_instance_type_from_region(
            self, accel_parameters_in_region)
        try:
            instance_type = self._session.compute.find_flavor(self._instance_type_name).id
        except _openstack.exceptions.ResourceNotFound:
            raise _exc.CSPConfigurationException(
                ("Failed to get flavor information for CSP '%s':\n"
                 "The flavor '%s' is not available in your CSP account. "
                 "Please contact you CSP to subscribe to this flavor.") %
                (self._provider, self._instance_type_name))

        return instance_type

    def _wait_instance_ready(self):
        """
        Wait until instance is ready.
        """
        # Waiting for the instance provisioning
        try:
            self._instance = self._session.compute.wait_for_server(self._instance)
        except _openstack.exceptions.SDKException as exception:
            self._instance = self._get_instance()
            try:
                msg = self._instance.fault.message
            except AttributeError:
                msg = exception
            raise _exc.CSPInstanceException("CSP exception", exc=msg)

        # Check instance status
        state = self._get_instance_status()
        if state.lower() == "error":
            self.stop_instance()
            raise _exc.CSPInstanceException("Instance has an invalid status: %s", state)

    def _start_new_instance(self):
        """
        Start a new instance.

        Returns:
            object: Instance
            str: Instance ID
        """
        instance = self._session.compute.create_server(
            name=self._get_instance_name(),
            image_id=self._image_id, flavor_id=self._instance_type,
            key_name=self._ssh_key, security_groups=[{"name": self._security_group}])

        return instance, instance.id

    def _start_existing_instance(self, state):
        """
        Start a existing instance.

        Args:
            state (str): Status of the instance.
        """
        if state.lower() != "active":
            self._session.start_server(self._instance)

    def _terminate_instance(self):
        """
        Terminate and delete instance.
        """
        if not self._session.delete_server(self._instance, wait=True):
            raise _exc.CSPInstanceException('Unable to delete instance.')

    def _pause_instance(self):
        """
        Pause instance.
        """
        # TODO: Implement pause instance support, actually terminates. shutdown ?
        self._terminate_instance()
