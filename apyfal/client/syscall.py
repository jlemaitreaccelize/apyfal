# coding=utf-8
"""Accelerator system call client."""

import json as _json
import os.path as _os_path
from subprocess import Popen as _Popen, PIPE as _PIPE
from uuid import uuid4 as _uuid

import apyfal.exceptions as _exc
from apyfal.client import AcceleratorClient as _Client
import apyfal.configuration as _cfg
import apyfal._utilities as _utl


def _call(command, **exc_args):
    """
    Call command in subprocess.

    Args:
        command (str or list or tuple): Command to call.
        exc_args: Extra arguments for exception to raise
            if error.

    Raises:
        apyfal.exceptions.ClientRuntimeException:
            Error while calling command.
    """
    try:
        process = _Popen(
            command, stdout=_PIPE, stderr=_PIPE, universal_newlines=True)
        outputs = process.communicate()
        in_error = process.returncode
    except OSError as exception:
        in_error = True
        outputs = [str(exception)]
    if in_error:
        raise _exc.ClientRuntimeException(exc='\n'.join(
            [command if isinstance(command, str) else ' '.join(command)] +
            [output for output in outputs if output]), **exc_args)


def _systemctl(command, *services):
    """Start or stop service using systemctl

    Args:
        services (str): service name.
        command (str): "start" or "stop"
    """
    for service in services:
        _call(['sudo', 'systemctl', command, '%s.service' % service],
              gen_msg=('unable_to_named', command, '%s service' % service))


class SysCallClient(_Client):
    """
    Accelerator client.

    Args:
        accelerator (str): Name of the accelerator you want to initialize,
            to know the accelerator list please visit "https://accelstore.accelize.com".
        client_type (str): Type of client. Default to "SysCall".
        accelize_client_id (str): Accelize Client ID.
            Client ID is part of the access key you can generate on
            "https:/accelstore.accelize.com/user/applications".
        accelize_secret_id (str): Accelize Secret ID. Secret ID come with client_id.
        config (str or apyfal.configuration.Configuration or file-like object):
            Can be Configuration instance, apyfal.storage URL, paths, file-like object.
            If not set, will search it in current working directory, in current
            user "home" folder. If none found, will use default configuration values.
    """

    #: Client type
    NAME = 'SysCall'

    # Temporary dir for JSON files
    _JSON_DIR = (
        '/dev/shm/apyfal_cache/%s' if _os_path.isdir('/dev/shm') else
        '/tmp/apyfal_cache/%s')

    def __init__(self, *args, **kwargs):
        if not _cfg.accelerator_executable_available():
            # Need accelerator executable to run
            raise _exc.HostConfigurationException(
                gen_msg='no_host_found')

        _Client.__init__(self, *args, **kwargs)

        # Initialize JSON temporary dir
        _utl.makedirs(self._JSON_DIR[:-2], exist_ok=True)

    def _start(self, datafile, info_dict, parameters):
        """
        Client specific start implementation.

        Args:
            datafile (str): Input file.
            info_dict (bool): Returns response dict.
            parameters (dict): Parameters dict.

        Returns:
            dict or None: response.
        """
        # Initialize metering
        self._init_metering(parameters)

        # Run and return response
        return self._run_executable(
            mode='0',
            input_file=datafile,
            input_json='start_input.json',
            output_json='start_output.json' if info_dict else None,
            parameters=parameters,
        )

    def _process(self, file_in, file_out, parameters):
        """
        Client specific process implementation.

        Args:
            file_in (str): Input file.
            file_out (str): Output file.
            parameters (dict): Parameters dict.

        Returns:
            dict: response dict.
        """
        return self._run_executable(
            mode='1',
            input_file=file_in,
            output_file=file_out,
            input_json='process_input.json',
            output_json='process_output.json',
            parameters=parameters,
            extra_args=['-v4'],
        )

    def _stop(self, info_dict):
        """
        Client specific stop implementation.

        Args:
            info_dict (bool): Returns response dict.

        Returns:
            dict or None: response.
        """
        if not _cfg.accelerator_executable_available():
            # Don't try to stop accelerator if not present
            return

        response = self._run_executable(
            mode='2',
            output_json='stop_output.json' if info_dict else None
        )

        # Stop services
        # TODO: Better to not stop services ?
        _systemctl('stop', 'meteringclient', 'meteringsession')

        # Get optional information
        return response

    @classmethod
    def _run_executable(
            cls, mode, input_file=None, output_file=None, input_json=None,
            output_json=None, parameters=None, extra_args=None):
        """
        Run accelerator executable.

        Args:
            mode (str): Accelerator mode ("0": start, "1": process, "2": stop)
            input_file (str): Input data file path.
            output_file (str): Output data file path.
            input_json (str): Input JSON file path.
            output_json: (str): Output JSON file path.
            parameters (dict): Parameters dict.
            extra_args (list of str): Extra accelerator arguments.

        Returns:
            dict or None: Content of output_json if any.
        """
        # Command base
        command = ['sudo', _cfg.ACCELERATOR_EXECUTABLE, '-m', mode]

        # Add extra command line arguments
        if extra_args:
            command.extend(extra_args)

        # Input file
        if input_file:
            command += ['-i', input_file]

        # Output file
        if output_file:
            command += ['-o', output_file]

        # Input JSON file
        if input_json and parameters:
            input_json = cls._JSON_DIR % input_json
            with open(input_json, 'wt') as json_input_file:
                _json.dump(parameters, json_input_file)
            command += ['-j', input_json]

        # Output JSON file
        if output_json:
            output_json = cls._JSON_DIR % output_json
            command += ['-p', output_json]

        # Run command
        _call(command)

        # Get result from output JSON file
        if output_json:
            with open(output_json, 'rt') as json_output_file:
                return _json.load(json_output_file)

    @staticmethod
    def _init_metering(parameters):
        """Initialize metering services.

        Args:
            parameters (dict): start parameters.
        """
        # Stop services
        _systemctl(
            'stop', 'accelerator', 'meteringsession', 'meteringclient')

        # Clear cache
        _call(['sudo', 'rm', _cfg.METERING_TMP_DIR])

        # Legacy metering: Generate metering configuration file
        first_call = True
        for key, value in (('USER_ID', parameters['env'].get('client_id')),
                           ('SESSION_ID', _uuid()),
                           ('AFI', parameters['env'].get('AGFI'))):
            if not value:
                continue
            _call(['sudo', 'echo', '"%s=%s"' % (key, value),
                   '>' if first_call else '>>',
                   _cfg.METERING_CLIENT_CONFIG])
            first_call = False

        # New metering: Generate metering configuration file
        if 'client_id' in parameters['env']:
            # Set right
            _call(['sudo', 'chmod', 'a+wr', _cfg.CREDENTIALS_JSON])
            with open(_cfg.CREDENTIALS_JSON, 'wb') as credential_file:
                _json.dump(
                    {key: parameters['env'][key]
                     for key in ('client_id', 'client_secret')},
                    credential_file)

        # Restart services
        _systemctl(
            'start', 'accelerator', 'meteringclient', 'meteringsession')