# coding=utf-8
"""Amazon Web Services"""

from copy import deepcopy as _deepcopy
from json import dumps as _json_dumps
import time as _time

import boto3 as _boto3
import botocore.exceptions as _boto_exceptions

from acceleratorAPI.csp import CSPGenericClass as _CSPGenericClass
import acceleratorAPI.configuration as _cfg
import acceleratorAPI.exceptions as _exc
import acceleratorAPI._utilities as _utl
from acceleratorAPI._utilities import get_logger as _get_logger


class AWSClass(_CSPGenericClass):
    """AWS CSP Class

    Args:
        provider (str): Cloud service provider name. Default to "AWS".
        config (str or acceleratorAPI.configuration.Configuration): Configuration file path or instance.
            If not set, will search it in current working directory, in current
            user "home" folder. If none found, will use default configuration values.
        client_id (str): AWS Access Key ID.
        secret_id (str): AWS Secret Access Key.
        region (str): AWS region. Needs a EC2 region supporting instances with FPGA devices.
        instance_type (str): AWS EC2 Instance type. Default defined by accelerator.
        ssh_key (str): AWS Key pair. Default to 'AccelizeAWSKeyPair'.
        security_group: AWS Security group. Default to 'AccelizeSecurityGroup'.
        instance_id (str): Instance ID of an already existing AWS EC2 instance to use.
            If not specified, create a new instance.
        instance_ip (str): IP or URL address of an already existing AWS EC2 instance to use.
            If not specified, create a new instance.
        role (str): AWS IAM role. Generated to allow instance to load AGFI (FPGA bitstream).
            Default to 'AccelizeRole'.
        stop_mode (str or int): Define the "stop" method behavior.
            Default to 'term' if new instance, or 'keep' if already existing instance.
            See "stop_mode" property for more information and possible values.
        exit_instance_on_signal (bool): If True, exit instance
            on OS exit signals. This may help to not have instance still running
            if Python interpreter is not exited properly. Note: this is provided for
            convenience and does not cover all exit case like process kill and
            may not work on all OS.
    """
    #: Provider name to use
    NAME = 'AWS'

    #: AWS Website
    DOC_URL = "https://aws.amazon.com"

    STATUS_RUNNING = 'running'
    STATUS_STOPPED = 'stopped'
    STATUS_STOPPING = 'stopping'

    _INFO_NAMES = _CSPGenericClass._INFO_NAMES.copy()
    _INFO_NAMES.add('_role')

    def __init__(self, config=None,  role=None, **kwargs):
        config = _cfg.create_configuration(config)
        _CSPGenericClass.__init__(self, config=config, **kwargs)

        # Get AWS specific arguments
        self._role = config.get_default(
            'csp', 'role', overwrite=role,
            default=self._default_parameter_value('Role'))

        # Load session
        self._session = _boto3.session.Session(
            aws_access_key_id=self._client_id,
            aws_secret_access_key=self._secret_id,
            region_name=self._region
        )

    @staticmethod
    def _handle_boto_exception(exception, filter_error_codes=None,
                               exception_msg=None):
        """
        Handle Boto exceptions.

        Args:
            exception (botocore.exceptions.ClientError): exception to handle
            filter_error_codes (list of str or str): AWS error code to filter.
            exception_msg (str): Message of the exception to raise in error
                code not in filter

        Raises:
            acceleratorAPI.exceptions.CSPInstanceException:
                error code not in filter_error_codes
        """
        # Try to get error code and message
        try:
            error_dict = exception.response['Error']
            error_code = error_dict['Code']
        except (AttributeError, KeyError):
            raise _exc.CSPInstanceException(
                exception_msg, exc=exception)

        # Converts single str to tuple
        if filter_error_codes is None:
            filter_error_codes = ()
        elif isinstance(filter_error_codes, str):
            filter_error_codes = (filter_error_codes,)

        # Raises if not in filter
        if error_code not in filter_error_codes:
            raise _exc.CSPInstanceException(
                exception_msg, exc=error_dict['Message'])

    def _check_credential(self):
        """
        Check CSP credentials.

        Raises:
            acceleratorAPI.exceptions.CSPAuthenticationException:
                Authentication failed.
        """
        ec2_client = self._session.client('ec2')
        try:
            ec2_client.describe_key_pairs()
        except ec2_client.exceptions.ClientError as exception:
            raise _exc.CSPAuthenticationException(exc=exception)

    def _init_key_pair(self):
        """
        Initialize key pair.

        Returns:
            bool: True if reuse existing key
        """
        ec2_client = self._session.client('ec2')

        # Checks if Key pairs exists, needs to get the full pairs list
        # and compare in lower case because Boto perform its checks case sensitive
        # and AWS use case insensitive names.
        try:
            key_pairs = ec2_client.describe_key_pairs()
        except ec2_client.exceptions.ClientError as exception:
            self._handle_boto_exception(exception)

        name_lower = self._ssh_key.lower()
        for key_pair in key_pairs['KeyPairs']:
            key_pair_name = key_pair['KeyName']
            if key_pair_name.lower() == name_lower:
                self._ssh_key = key_pair_name
                return True

        # Key does not exist on the CSP, create it
        ec2_resource = self._session.resource('ec2')
        try:
            key_pair = ec2_resource.create_key_pair(KeyName=self._ssh_key)
        except _boto_exceptions.ClientError as exception:
            self._handle_boto_exception(exception)

        _utl.create_ssh_key_file(self._ssh_key, key_pair.key_material)

        return False

    def _init_policy(self, policy):
        """
        Initialize CSP policy.

        Args:
            policy:
        """
        # Create a policy
        policy_document = _json_dumps({
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "AllowFpgaCommands",
                    "Effect": "Allow",
                    "Action": [
                        "ec2:AssociateFpgaImage",
                        "ec2:DisassociateFpgaImage",
                        "ec2:DescribeFpgaImages"
                    ],
                    "Resource": ["*"]
                }
            ]
        })

        iam_client = self._session.client('iam')
        try:
            iam_client.create_policy(
                PolicyName=policy, PolicyDocument=policy_document)

        except iam_client.exceptions.EntityAlreadyExistsException:
            # TODO: check if cached properly
            pass
        else:
            _get_logger().info(
                "Created policy on AWS named %s to allow FPGA loading ", policy)

        iam_client = self._session.client('iam')
        response = iam_client.list_policies(
            Scope='Local', OnlyAttached=False, MaxItems=100)
        for policy_item in response['Policies']:
            if policy_item['PolicyName'] == policy:
                return policy_item['Arn']

        raise _exc.CSPConfigurationException(
            "Failed to create policy. Unable to find policy 'Arn'.")

    def _init_role(self):
        """
        Initialize CSP role.
        """
        assume_role_policy_document = _json_dumps({
            "Version": "2012-10-17",
            "Statement": {
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }
        })

        iam_resource = self._session.resource('iam')
        try:
            role = iam_resource.create_role(
                RoleName=self._role,
                AssumeRolePolicyDocument=assume_role_policy_document,
                Description='Created automatically'
            )

        except _boto_exceptions.ClientError:
            # TODO: to catch properly
            pass
        else:
            _get_logger().info(
                "Created role on AWS named %s to allow FPGA loading ", role)

        iam_client = self._session.client('iam')
        arn = iam_client.get_role(RoleName=self._role)['Role']['Arn']

        return arn

    def _attach_role_policy(self, policy_arn):
        """
        Attach policy to role.

        Args:
            policy_arn (str): Policy ARN
        """
        iam_client = self._session.client('iam')
        try:
            # Create a policy
            iam_client.attach_role_policy(
                PolicyArn=policy_arn, RoleName=self._role)

        except iam_client.exceptions.EntityAlreadyExistsException:
            # TODO: check if cached properly
            return
        _get_logger().info("Attached policy '%s' to role '%s'.", policy_arn, self._role)

    def _init_instance_profile(self):
        """
        Initialize instance profile.
        """
        instance_profile_name = 'AccelizeLoadFPGA'

        iam_client = self._session.client('iam')
        try:
            instance_profile = iam_client.create_instance_profile(
                InstanceProfileName=instance_profile_name)

        except iam_client.exceptions.EntityAlreadyExistsException:
            # TODO: check if cached properly

            # TODO: Get already existing instance_profile and then attach role in both cases
            pass

        else:
            _time.sleep(5)

            # Attach role to instance profile
            instance_profile.add_role(RoleName=self._role)
            _get_logger().info(
                "Attach role '%s' to instance profile '%s' to allow FPGA loading ",
                self._role, instance_profile_name)

    def _init_security_group(self):
        """
        Initialize CSP security group.
        """
        # Get list of security groups
        # Checks if Key pairs exists, like for key pairs
        # needs  case insensitive names check
        ec2_client = self._session.client('ec2')
        try:
            security_groups = ec2_client.describe_security_groups()
        except ec2_client.exceptions.ClientError as exception:
            self._handle_boto_exception(exception)

        name_lower = self._security_group.lower()
        group_exists = False
        for security_group in security_groups['SecurityGroups']:
            group_name = security_group['GroupName']
            if group_name.lower() == name_lower:
                # Update name
                self._security_group = group_name

                # Get group ID
                security_group_id = security_group['GroupId']

                # Mark as existing
                group_exists = True
                break

        # Try to create security group if not exist
        if not group_exists:
            # Get VPC
            vpc_id = ec2_client.describe_vpcs().get('Vpcs', [{}])[0].get('VpcId', '')

            try:
                response = ec2_client.create_security_group(
                    GroupName=self._security_group,
                    Description="Generated by Accelize acceleratorAPI", VpcId=vpc_id)
            except ec2_client.exceptions.ClientError as exception:
                self._handle_boto_exception(exception)

            # Get group ID
            security_group_id = response['GroupId']

            _get_logger().info("Created security group with ID %s in vpc %s", security_group_id, vpc_id)

        # Add host IP to security group if not already done
        public_ip = _utl.get_host_public_ip()

        try:
            ec2_client.authorize_security_group_ingress(
                GroupId=security_group_id,
                IpPermissions=[
                    {'IpProtocol': 'tcp',
                     'FromPort': 80,
                     'ToPort': 80,
                     'IpRanges': [{'CidrIp': public_ip}]
                     },
                    {'IpProtocol': 'tcp',
                     'FromPort': 22,
                     'ToPort': 22,
                     'IpRanges': [{'CidrIp': public_ip}]
                     }
                ])
        except ec2_client.exceptions.ClientError as exception:
            self._handle_boto_exception(exception, 'InvalidPermission.Duplicate')

        _get_logger().info("Added in security group '%s': SSH and HTTP for IP %s.",
                           self._security_group, public_ip)

    def _get_instance(self):
        """
        Returns current instance.

        Returns:
            object: Instance
        """
        return self._session.resource('ec2').Instance(self._instance_id)

    def _get_public_ip(self):
        """
        Read current instance public IP from CSP instance.

        Returns:
            str: IP address
        """
        try:
            return self._instance.public_ip_address
        except _boto_exceptions.ClientError as exception:
            raise _exc.CSPInstanceException("Could not return instance URL", exc=exception)

    def _get_private_ip(self):
        """
        Read current instance private IP from CSP instance.

        Returns:
            str: IP address
        """
        try:
            return self._instance.private_ip_address
        except _boto_exceptions.ClientError as exception:
            raise _exc.CSPInstanceException("Could not return instance URL", exc=exception)

    def _get_status(self):
        """
        Returns current status of current instance.

        Returns:
            str: Status
        """
        try:
            instance_state = self._instance.state
        except _boto_exceptions.ClientError as exception:
            raise _exc.CSPInstanceException(
                "Could not find an instance with ID %s", self._instance_id, exc=exception)
        return instance_state["Name"]

    def _get_config_env_from_region(self, accel_parameters_in_region):
        """
        Read accelerator parameters and get configuration environment.

        Args:
            accel_parameters_in_region (dict): AcceleratorClient parameters
                for the current CSP region.

        Returns:
            dict: configuration environment
        """
        return {'AGFI': accel_parameters_in_region['fpgaimage']}

    def get_configuration_env(self, **kwargs):
        """
        Return environment to pass to
        "acceleratorAPI.accelerator.AcceleratorClient.start"
        "csp_env" argument.

        Args:
            kwargs:

        Returns:
            dict: Configuration environment.
        """
        currenv = _deepcopy(self._config_env)

        try:
            currenv['AGFI'] = kwargs['AGFI']
        except KeyError:
            pass
        else:
            import warnings
            warnings.warn(
                "Overwrite AGFI factory requirements with custom configuration:\n%s",
                _utl.pretty_dict(kwargs['AGFI']))
        return currenv

    def _create_instance(self):
        """
        Initialize and create instance.
        """
        policy_arn = self._init_policy('AccelizePolicy')
        self._init_role()
        self._init_instance_profile()
        self._attach_role_policy(policy_arn)
        self._init_security_group()

    def _start_new_instance(self):
        """
        Start a new instance.

        Returns:
            object: Instance
            str: Instance ID
        """
        instance = self._session.resource('ec2').create_instances(
            ImageId=self._image_id,
            InstanceType=self._instance_type,
            KeyName=self._ssh_key,
            SecurityGroups=[self._security_group],
            IamInstanceProfile={'Name': 'AccelizeLoadFPGA'},
            InstanceInitiatedShutdownBehavior='stop',
            TagSpecifications=[{
                'ResourceType': 'instance',
                'Tags': [
                    {'Key': 'Generated',
                     'Value': 'Accelize acceleratorAPI'},
                    {'Key': 'Name',
                     'Value': self._get_instance_name()}
                ]}],
            MinCount=1, MaxCount=1)[0]

        return instance, instance.id

    def _start_existing_instance(self, status):
        """
        Start a existing instance.

        Args:
            status (str): Status of the instance.
        """
        # Waiting for the instance stop if currently stopping
        if status == self.STATUS_STOPPING:
            with _utl.Timeout(self.TIMEOUT) as timeout:
                while True:
                    # Get instance status
                    status = self._status()
                    if status != self.STATUS_STOPPING:
                        break
                    elif timeout.reached():
                        raise _exc.CSPInstanceException(
                            "Timed out while waiting CSP instance stopping"
                            " (last status: %s)." % status)

        # If instance stopped, starts it
        if status == self.STATUS_STOPPED:
            self._instance.start()

        # If another status, raises error
        elif status != self.STATUS_RUNNING:
            raise _exc.CSPInstanceException(
                "Instance ID %s cannot be started because it is not in a valid status (%s).",
                self._instance_id, status)

    def _terminate_instance(self):
        """
        Terminate and delete instance.
        """
        if self._instance is not None:
            return self._instance.terminate()

    def _pause_instance(self):
        """
        Pause instance.
        """
        if self._instance is not None:
            return self._instance.stop()
