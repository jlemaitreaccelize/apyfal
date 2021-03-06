# coding=utf-8
"""Apyfal


Copyright 2018 Accelize

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
__version__ = "1.1.0"
__copyright__ = "Copyright 2018 Accelize"
__licence__ = "Apache 2.0"

from sys import version_info as _py
if (_py[0] < 2) or (_py[0] == 2 and _py[1] < 7) or (_py[0] == 3 and _py[1] < 4):
    from sys import version
    raise ImportError('Python %s is not supported by Apyfal' % version)

import apyfal.host as _hst
import apyfal.client as _clt
import apyfal.exceptions as _exc
import apyfal.configuration as _cfg
from apyfal._utilities import get_logger as _get_logger


# Makes get_logger available here for easy access
get_logger = _get_logger


class Accelerator(object):
    """
    This class provides the full accelerator features by handling
    Accelerator and its host.

    Args:
        accelerator (str): Name of the accelerator to initialize,
            to know the accelerator list please visit "https://accelstore.accelize.com".
        config (str or apyfal.configuration.Configuration or file-like object):
            Can be Configuration instance, apyfal.storage URL, paths, file-like object.
            If not set, will search it in current working directory, in current
            user "home" folder. If none found, will use default configuration values.
        accelize_client_id (str): Accelize Client ID.
            Client ID is part of the access key generated on
            "https:/accelstore.accelize.com/user/applications".
        accelize_secret_id (str): Accelize Secret ID. Secret ID come with xlz_client_id.
        host_type (str): Type of host to use.
        host_ip (str): IP or URL address of an already existing host to use.
            If not specified, create a new host.
        stop_mode (str or int): Host stop mode.
            Default to 'term' if new host, or 'keep' if already existing host.
            See "apyfal.host.Host.stop_mode" property for more
            information and possible values.
        host_kwargs: Keyword arguments related to specific host. See targeted host class
            to see full list of arguments.
    """
    def __init__(self, accelerator=None, config=None, accelize_client_id=None,
                 accelize_secret_id=None, host_type=None, host_ip=None,
                 stop_mode='term', **host_kwargs):

        # Initialize configuration
        config = _cfg.create_configuration(config)

        # Create host object
        host_type = host_type or config['host']['host_type']
        if host_type is not None:
            # Use a remote host
            self._host = _hst.Host(
                host_type=host_type, config=config, host_ip=host_ip,
                stop_mode=stop_mode, **host_kwargs)

            # Remote control use REST client
            client_type = 'REST'

            # Get updated URL if any
            try:
                host_ip = self._host.url
            except _exc.HostException:
                host_ip = None
        else:
            # Use local host
            self._host = None

            # Use default local client if not specified IP
            client_type = 'REST' if host_ip else None

        # Create AcceleratorClient object
        self._client = _clt.AcceleratorClient(
            accelerator=accelerator, client_type=client_type,
            accelize_client_id=accelize_client_id, host_ip=host_ip,
            accelize_secret_id=accelize_secret_id, config=config)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.stop()

    def __del__(self):
        self.stop()

    @property
    def client(self):
        """
        Accelerator client.

        Returns:
            apyfal.client.AcceleratorClient: Accelerator client
        """
        return self._client

    @property
    def host(self):
        """
        Accelerator host.

        Returns:
            apyfal.host.Host subclass: Host
        """
        return self._host

    def start(self, stop_mode=None, datafile=None, info_dict=False, host_env=None, **parameters):
        """
        Starts and/or configure an accelerator.

        Args:
            stop_mode (str or int): Host stop mode. If not None, override current "stop_mode" value.
                See "apyfal.host.Host.stop_mode" property for more
                information and possible values.
            datafile (str or file-like object): Depending on the accelerator,
                a configuration data file need to be loaded before a process can be run.
                Can be apyfal.storage URL, paths, file-like object.
            info_dict (bool): If True, returns a dict containing information on
                configuration operation.
            parameters (str or dict): Accelerator configuration specific parameters
                Can also be a full configuration parameters dictionary
                (Or JSON equivalent as str literal or apyfal.storage URL to file)
                Parameters dictionary override default configuration values,
                individuals specific parameters overrides parameters dictionary values.
                Take a look to accelerator documentation for more information on possible parameters.

        Returns:
            dict: Optional, only if "info_dict" is True. AcceleratorClient response.
                  AcceleratorClient contain output information from  configuration operation.
                  Take a look to accelerator documentation for more information.
        """
        if self._host is not None:
            # Start host if needed (Do nothing if already started)
            self._host.start(accelerator=self._client.name, stop_mode=stop_mode)

            # Set accelerator URL to host URL
            self._client.url = self._host.url

            # Get environment
            host_env = self._host.get_configuration_env(**(host_env or dict()))

        # Configure accelerator if needed
        return self._client.start(datafile=datafile, host_env=host_env or dict(),
                                  info_dict=info_dict, **parameters)

    def process(self, file_in=None, file_out=None, info_dict=False, **parameters):
        """
        Processes with accelerator.

        Args:
            file_in (str or file-like object): Input file to process.
                Can be apyfal.storage URL, paths, file-like object.
            file_out (str or file-like object): Output processed file.
                Can be apyfal.storage URL, paths, file-like object.
            info_dict (bool): If True, returns a dict containing information on
                process operation.
            parameters (str or dict): Accelerator process specific parameters
                Can also be a full process parameters dictionary
                (Or JSON equivalent as str literal or apyfal.storage URL to file)
                Parameters dictionary override default configuration values,
                individuals specific parameters overrides parameters dictionary values.
                Take a look to accelerator documentation for more information on possible parameters.

        Returns:
            dict: Result from process operation, depending used accelerator.
            dict: Optional, only if "info_dict" is True. AcceleratorClient response.
                AcceleratorClient contain output information from  process operation.
                Take a look accelerator documentation for more information.
        """
        _enable_logger = _get_logger().isEnabledFor(20)

        # Process file with accelerator
        process_result = self._client.process(
            file_in=file_in, file_out=file_out,
            info_dict=info_dict or _enable_logger, **parameters)

        if _enable_logger:
            # Logger case
            self._log_profiling_info(process_result)
            return process_result if info_dict else process_result[0]
        return process_result

    def stop(self, stop_mode=None, info_dict=False):
        """
        Stop accelerator session and accelerator host depending of the parameters

        Args:
            stop_mode (str or int): Host stop mode. If not None, override current "stop_mode" value.
                See "apyfal.host.Host.stop_mode" property for more
                information and possible values.
            info_dict (bool): If True, returns a dict containing information on
                stop operation.

        Returns:
            dict: Optional, only if "info_dict" is True. AcceleratorClient response.
                AcceleratorClient contain output information from  stop operation.
                Take a look to accelerator documentation for more information.
        """
        # Stops accelerator
        try:
            return self._client.stop(info_dict=info_dict)

        except (AttributeError, _exc.ClientException):
            return None

        # Stops host
        finally:
            if self._host is not None:
                try:
                    self._host.stop(stop_mode)
                except (AttributeError, _exc.HostException):
                    pass

    @staticmethod
    def _log_profiling_info(process_result):
        """
        Shows profiling and specific information in logger.

        Args:
            process_result (dict): result from AcceleratorClient.process
        """
        logger = _get_logger()

        try:
            app = process_result[1]['app']
        except KeyError:
            return None

        # Lazy import since not always called
        import json

        # Handle profiling info
        try:
            profiling = app['profiling']
        except KeyError:
            pass
        else:
            logger.info("Profiling information from result:")

            # Compute and show information only on DEBUG level
            values = dict()

            for key in ('wall-clock-time', 'fpga-elapsed-time', 'total-bytes-written', 'total-bytes-read'):
                try:
                    values[key] = float(profiling[key])
                except KeyError:
                    pass

            total_bytes = values.get('total-bytes-written', 0.0) + values.get('total-bytes-read', 0.0)
            global_time = values.get('wall-clock-time', 0.0)
            fpga_time = values.get('fpga-elapsed-time', 0.0)

            if global_time > 0.0:
                logger.info('- Wall clock time: %.3fs' % global_time)

            if global_time > 0.0:
                logger.info('- FPGA elapsed time: %.3fs' % fpga_time)

            if total_bytes > 0.0 and global_time > 0.0:
                logger.info("- Server processing bandwidths: %.1f MB/s",
                            total_bytes / global_time / 1024.0 / 1024.0)

            if total_bytes > 0.0 and fpga_time > 0.0:
                logger.info("- FPGA processing bandwidths: %.1f MB/s",
                            total_bytes / fpga_time / 1024.0 / 1024.0)

        # Handle Specific result
        try:
            specific = app['specific']
        except KeyError:
            pass
        else:
            if specific:
                logger.info("Specific information from result:\n%s",
                            json.dumps(specific, indent=4).replace('\\n', '\n')
                            .replace('\\t', '\t'))
