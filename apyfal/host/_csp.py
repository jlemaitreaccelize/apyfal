# coding=utf-8
"""Cloud Service Providers"""

from abc import abstractmethod as _abstractmethod
from datetime import datetime as _datetime

try:
    # Python 2
    from StringIO import StringIO as _StringIO
except ImportError:
    # Python 3
    from io import StringIO as _StringIO

from apyfal.host import Host as _Host
import apyfal.configuration as _cfg
import apyfal.exceptions as _exc
import apyfal._utilities as _utl
from apyfal._utilities import get_logger as _get_logger


class CSPHost(_Host):
    """This is base abstract class for all CSP classes.

    Args:
        host_type (str): Cloud service provider name.
        config (str or apyfal.configuration.Configuration or file-like object):
            Can be Configuration instance, apyfal.storage URL, paths, file-like object.
            If not set, will search it in current working directory, in current
            user "home" folder. If none found, will use default configuration values.
        client_id (str): CSP Access Key ID.
        secret_id (str): CSP Secret Access Key.
        region (str): CSP region. Needs a region supporting instances with FPGA devices.
        instance_type (str): CSP instance type. Default defined by accelerator.
        key_pair (str): CSP Key pair. Default to 'Accelize<HostName>KeyPair'.
        security_group: CSP Security group. Default to 'AccelizeSecurityGroup'.
        instance_id (str): Instance ID of an already existing CSP instance to use.
            If not specified, create a new instance.
        instance_name_prefix (str): Prefix to add to instance name.
        host_ip (str): IP or URL address of an already existing CSP instance to use.
            If not specified, create a new instance.
        stop_mode (str or int): Define the "stop" method behavior.
            Default to 'term' if new instance, or 'keep' if already existing instance.
            See "stop_mode" property for more information and possible values.
        init_config (bool or str or apyfal.configuration.Configuration or file-like object):
            Configuration file to pass to instance on initialization.
            This configuration file will be used as default for host side accelerator.
            If value is True, use 'config' configuration.
            If value is a configuration use this configuration.
            If value is None or False, don't passe any configuration file
            (This is default behavior).
    """
    #: Instance status when running
    STATUS_RUNNING = 'running'

    #: Instance status when stopped
    STATUS_STOPPED = 'stopped'

    #: Allowed ports for instance access
    ALLOW_PORTS = [22, 80]

    # Attributes returned as dict by "info" property
    _INFO_NAMES = _Host._INFO_NAMES.copy()
    _INFO_NAMES.update({
        'public_ip', 'private_ip', '_region', '_instance_type', '_instance_name',
        '_key_pair', '_security_group', '_instance_id', '_instance_type_name'})

    # Instance user home directory
    _HOME = '/home/centos'

    def __init__(self, client_id=None, secret_id=None, region=None,
                 instance_type=None, key_pair=None, security_group=None, instance_id=None,
                 instance_name_prefix=None, init_config=None, **kwargs):
        _Host.__init__(self, **kwargs)

        # Default some attributes
        self._session = None
        self._instance = None
        self._config_env = {}
        self._image_id = None
        self._image_name = None
        self._instance_name = None
        self._instance_type = None
        self._instance_type_name = None

        # Read configuration from file
        section = self._config[self._config_section]
        self._client_id = client_id or section['client_id']
        self._secret_id = secret_id or section['secret_id']
        self._region = region or section['region']
        self._instance_type = instance_type or section['instance_type']
        self._instance_id = instance_id or section['instance_id']
        self._instance_name_prefix = (
                instance_name_prefix or
                section['instance_name_prefix'] or '')

        self._key_pair = (
            key_pair or section['key_pair'] or
            self._default_parameter_value('KeyPair', include_host=True))

        self._security_group = (
            security_group or section['security_group'] or
            self._default_parameter_value('SecurityGroup'))

        self.stop_mode = (
            kwargs.get('stop_mode') or section['stop_mode'] or
            ('keep' if instance_id or kwargs.get('host_ip') else 'term'))

        self._init_config = init_config or section['init_config']

        # Checks mandatory configuration values
        self._check_arguments('region')

        if (self._client_id is None and
                self._instance_id is None and self._url is None):
            raise _exc.HostConfigurationException(
                "Need at least 'client_id', 'instance_id' or 'host_ip' "
                "argument. See documentation for more information.")

    @property
    def public_ip(self):
        """
        Public IP of the current instance.

        Returns:
            str: IP address

        Raises:
            apyfal.exceptions.HostRuntimeException:
                No instance from which get IP.
        """
        if self._instance is None:
            raise _exc.HostRuntimeException(gen_msg='no_instance')
        return self._get_public_ip()

    @_abstractmethod
    def _get_public_ip(self):
        """
        Read current instance public IP from CSP instance.

        Returns:
            str: IP address
        """

    @property
    def key_pair(self):
        """
        SSH Key pair linked to this instance.

        Returns:
            str: Name of key pair.
        """
        return self._key_pair

    @property
    def private_ip(self):
        """
        Private IP of the current instance.

        Returns:
            str: IP address

        Raises:
            apyfal.exceptions.HostRuntimeException:
                No instance from which get IP.
        """
        if self._instance is None:
            raise _exc.HostRuntimeException(gen_msg='no_instance')
        return self._get_private_ip()

    @_abstractmethod
    def _get_private_ip(self):
        """
        Read current instance private IP from CSP instance.

        Returns:
            str: IP address
        """

    @property
    def instance_id(self):
        """
        ID of the current instance.

        Returns:
            str: ID
        """
        return self._instance_id

    @property
    def instance_name(self):
        """
        Name of the current instance.

        Returns:
            str: Name
        """
        return self._instance_name

    @_abstractmethod
    def _check_credential(self):
        """
        Check CSP credentials.

        Raises:
            apyfal.exceptions.HostAuthenticationException:
                Authentication failed.
        """

    def _status(self):
        """
        Returns current status of current instance.

        Returns:
            str: Status

        Raises:
            apyfal.exceptions.HostRuntimeException:
                No instance from which get status.
        """
        if self._instance_id is None:
            raise _exc.HostRuntimeException(gen_msg='no_instance')

        # Update instance
        self._instance = self._get_instance()

        if self._instance is None:
            raise _exc.HostRuntimeException(
                gen_msg=('no_instance_id', self._instance_id))

        # Read instance status
        return self._get_status()

    @_abstractmethod
    def _get_status(self):
        """
        Returns current status of current instance.

        Returns:
            str: Status
        """

    @_abstractmethod
    def _get_instance(self):
        """
        Returns current instance.

        Returns:
            object: Instance
        """

    @_abstractmethod
    def _init_key_pair(self):
        """
        Initializes key pair.

        Returns:
            bool: True if reuses existing key
        """

    def start(self, accelerator=None, accel_parameters=None, stop_mode=None):
        """
        Start instance if not already started. Create instance if necessary.

        Needs "accel_client" or "accel_parameters".

        Args:
            accelerator (str): Name of the accelerator.
            accel_parameters (dict): Can override parameters from accelerator client.
            stop_mode (str or int): See "stop_mode" property for more information.
        """
        # Updates stop mode
        self.stop_mode = stop_mode

        # Get parameters from accelerator
        self._set_accelerator_requirements(
            accelerator, accel_parameters)

        # Starts instance only if not already started
        if self._url is None:

            # Checks CSP credential
            self._check_credential()

            # Creates and starts instance if not exists
            if self.instance_id is None:
                _get_logger().info("Configuring %s instance...", self._host_type)

                # Configure and create instance
                reuse_key = self._init_key_pair()
                if not reuse_key:
                    _get_logger().info(_utl.gen_msg(
                        "created_named", "key pair", self._key_pair))

                try:
                    self._create_instance()
                except _exc.HostException as exception:
                    self._stop_silently(exception)
                    raise

                try:
                    self._instance, self._instance_id = self._start_new_instance()
                except _exc.HostException as exception:
                    self._stop_silently(exception)
                    raise

                _get_logger().info(_utl.gen_msg(
                    'created_named', 'instance', self._instance_id))

            # If exists, starts it directly
            else:
                status = self._status()
                self._start_existing_instance(status)

            # Waiting for instance provisioning
            _get_logger().info("Waiting instance provisioning...")
            try:
                self._wait_instance_ready()
            except _exc.HostException as exception:
                self._stop_silently(exception)
                raise

            # Update instance URL
            self._url = _utl.format_url(self.public_ip)

            # Waiting for the instance to boot
            _get_logger().info("Waiting instance boot...")
            self._wait_instance_boot()

            _get_logger().info("Instance ready")

        # If URL exists, checks if reachable
        elif not _utl.check_url(self._url):
            raise _exc.HostRuntimeException(
                gen_msg=('unable_reach_url', self._url))

    @_abstractmethod
    def _create_instance(self):
        """
        Initializes and creates instance.
        """

    @_abstractmethod
    def _start_new_instance(self):
        """
        Starts a new instance.

        Returns:
            object: Instance
            str: Instance ID
        """

    @_abstractmethod
    def _start_existing_instance(self, status):
        """
        Starts a existing instance.

        Args:
            status (str): Status of the instance.
        """

    def _wait_instance_ready(self):
        """
        Waits until instance is ready.
        """
        # Waiting for the instance provisioning
        with _utl.Timeout(self.TIMEOUT) as timeout:
            while True:
                # Get instance status
                status = self._status()
                if status == self.STATUS_RUNNING:
                    return
                elif timeout.reached():
                    raise _exc.HostRuntimeException(
                        gen_msg=('timeout_status', "provisioning", status))

    def _wait_instance_boot(self):
        """Waits until instance has booted and webservice is OK

        Raises:
            apyfal.exceptions.HostRuntimeException:
                Timeout while booting."""
        if not _utl.check_url(self._url, timeout=self.TIMEOUT):
            raise _exc.HostRuntimeException(
                gen_msg=('timeout', "boot"))

    def _get_instance_name(self):
        """Returns name to use as instance name

        Returns:
            str: name with format
                'Accelize_<AcceleratorName>_<DateTime>'"""
        if self._instance_name is None:

            self._instance_name = '_'.join(
                name for name in (
                    self._instance_name_prefix,
                    'accelize', self._accelerator,
                    _datetime.now().strftime('%y%m%d%H%M%S'))
                if name)

        return self._instance_name

    def stop(self, stop_mode=None):
        """
        Stop instance accordingly with the current stop_mode.
        See "stop_mode" property for more information.

        Args:
            stop_mode (str or int): If not None, override current "stop_mode" value.
        """
        # No instance to stop (Avoid double call with __exit__ + __del__)
        if self._instance is None:
            return

        # Define stop mode
        if stop_mode is None:
            stop_mode = self._stop_mode

        # Keep instance alive
        if stop_mode == 'keep':
            import warnings
            warnings.warn(
                "Instance '%s' is still running" % self.instance_id, Warning)
            return

        # Checks if instance to stop
        try:
            self._status()
        except _exc.HostRuntimeException:
            return

        # Terminates and delete instance completely
        if stop_mode == 'term':
            self._terminate_instance()
            self._instance = None
            _get_logger().info("Instance '%s' has been terminated", self._instance_id)

        # Pauses instance and keep it alive
        else:
            self._pause_instance()
            self._instance = None
            _get_logger().info("Instance '%s' has been stopped", self._instance_id)

    @_abstractmethod
    def _terminate_instance(self):
        """
        Terminates and deletes instance.
        """

    @_abstractmethod
    def _pause_instance(self):
        """
        Pauses instance.
        """

    def _stop_silently(self, exception):
        """
        Terminates and deletes instance ignoring errors.

        Args:
            exception(Exception): If provided, augment message
                of this exception with CSP help.
        """
        # Augment exception message
        if exception is not None:
            self._add_csp_help_to_exception_message(exception)

        # Force stop instance, ignore exception if any
        try:
            self._terminate_instance()
        except _exc.HostException:
            pass

    def _set_accelerator_requirements(self, accelerator=None, accel_parameters=None):
        """
        Configures instance with accelerator client parameters.

        Needs "accel_client" or "accel_parameters".

        Args:
            accelerator (str): Name of the accelerator
            accel_parameters (dict): Can override parameters from accelerator client.

        Raises:
            apyfal.exceptions.HostConfigurationException:
                Parameters are not valid..
        """
        # Get parameters
        parameters = dict()
        if accelerator is not None:
            parameters.update(self._config.get_host_requirements(
                self._host_type, accelerator))

        if accel_parameters is not None:
            parameters.update(accel_parameters)

        # Check if region is valid
        if self._region not in parameters.keys():
            raise _exc.HostConfigurationException(
                "Region '%s' is not supported. Available regions are: %s" % (
                    self._region, ', '.join(
                        region for region in parameters if region != 'accelerator')))

        # Get accelerator name
        self._accelerator = parameters['accelerator']

        # Set parameters for current region
        region_parameters = parameters[self._region]
        self._image_id = self._get_image_id_from_region(region_parameters)
        self._instance_type = self._get_instance_type_from_region(region_parameters)
        self._config_env = self._get_config_env_from_region(region_parameters)

    @staticmethod
    def _get_image_id_from_region(accel_parameters_in_region):
        """
        Read accelerator parameters and get image id.

        Args:
            accel_parameters_in_region (dict): AcceleratorClient parameters
                for the current CSP region.

        Returns:
            str: image_id
        """
        return accel_parameters_in_region['image']

    @staticmethod
    def _get_instance_type_from_region(accel_parameters_in_region):
        """
        Read accelerator parameters and instance type.

        Args:
            accel_parameters_in_region (dict): AcceleratorClient parameters
                for the current CSP region.

        Returns:
            str: instance_type
        """
        return accel_parameters_in_region['instancetype']

    def _get_config_env_from_region(self, accel_parameters_in_region):
        """
        Read accelerator parameters and get configuration environment.

        Args:
            accel_parameters_in_region (dict): AcceleratorClient parameters
                for the current CSP region.

        Returns:
            dict: configuration environment
        """
        return self._config_env

    @property
    def _user_data(self):
        """
        Generate a shell script to initialize instance.

        Returns:
            str: shell script.
        """
        if self._init_config is None:
            return None

        config = (self._config if self._init_config is True else
                  self._init_config)

        # Initialize file with shebang
        commands = ["#!/usr/bin/env bash"]

        # Write default configuration file
        stream = _StringIO()
        _cfg.create_configuration(config).write(stream)
        stream.seek(0)

        commands += [
            "cat << EOF > %s/accelerator.conf" % self._HOME,
            stream.read(), "EOF"]

        return '\n'.join(commands).encode()
