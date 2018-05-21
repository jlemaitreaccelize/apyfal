# coding=utf-8
"""acceleratorAPI.client tests"""
import collections
import io
import gc
import json
import sys

import pytest


def test_acceleratorclient_check_accelize_credential():
    """Tests AcceleratorClient._check_accelize_credential

    Test parts that needs credentials"""
    from acceleratorAPI.configuration import Configuration
    from acceleratorAPI.client import AcceleratorClient
    from acceleratorAPI.exceptions import AcceleratorAuthenticationException

    # Load user configuration
    config = Configuration()

    # Skip test if Accelize credentials not available
    if not config.has_accelize_credential():
        pytest.skip('Accelize Credentials required')

    # Test: Valid credentials
    # Assuming Accelize credentials in configuration file are valid, should pass
    # Called Through AcceleratorClient.__init__
    AcceleratorClient('dummy', config=config)

    # Test: Keep same client_id but use bad secret_id
    with pytest.raises(AcceleratorAuthenticationException):
        AcceleratorClient('dummy', config=config, secret_id='bad_secret_id')


def test_acceleratorclient_check_accelize_credential_no_cred():
    """Tests AcceleratorClient._check_accelize_credential

    Test parts that don't needs credentials"""
    from acceleratorAPI.configuration import Configuration
    from acceleratorAPI.client import AcceleratorClient
    import acceleratorAPI.exceptions as exc

    # Load user configuration but remove any accelize credential
    # information from it
    config = Configuration()
    config.remove_section('accelize')

    # Test: No credential provided
    with pytest.raises(exc.AcceleratorConfigurationException):
        AcceleratorClient('dummy', config=config)

    # Test: Bad client_id
    with pytest.raises(exc.AcceleratorAuthenticationException):
        AcceleratorClient('dummy', client_id='bad_client_id',
                          secret_id='bad_secret_id', config=config)


def test_acceleratorclient_is_alive():
    """Tests AcceleratorClient._raise_for_status"""
    from acceleratorAPI.client import AcceleratorClient
    from acceleratorAPI.exceptions import AcceleratorRuntimeException

    # Mock some accelerators parts
    class DummyAccelerator(AcceleratorClient):
        """Dummy AcceleratorClient"""

        def __init__(self, url=None):
            """Do not initialize"""
            self._url = url

        def __del__(self):
            """Do nothing"""

    # Test: No instance
    accelerator = DummyAccelerator()
    with pytest.raises(AcceleratorRuntimeException):
        accelerator.is_alive()

    # Test: URL exists
    accelerator = DummyAccelerator(url='https://www.accelize.com')
    accelerator.is_alive()

    # Test: URL not exist
    accelerator = DummyAccelerator(url='https://www.url_that_not_exists.accelize.com')
    with pytest.raises(AcceleratorRuntimeException):
        accelerator.is_alive()


def test_acceleratorclient_raise_for_status():
    """Tests AcceleratorClient._raise_for_status"""
    from acceleratorAPI.client import AcceleratorClient
    from acceleratorAPI.exceptions import AcceleratorRuntimeException

    # Test: Result without error
    AcceleratorClient._raise_for_status({'app': {'status': 0, 'msg': ''}})

    # Test: Empty result
    with pytest.raises(AcceleratorRuntimeException):
        AcceleratorClient._raise_for_status({})

    # Test: Result with error
    with pytest.raises(AcceleratorRuntimeException):
        AcceleratorClient._raise_for_status({'app': {'status': 1, 'msg': 'error'}})


def test_acceleratorclient_get_requirements():
    """Tests AcceleratorClient.get_requirements"""
    from acceleratorAPI.configuration import Configuration
    from acceleratorAPI.client import AcceleratorClient
    from acceleratorAPI.exceptions import AcceleratorConfigurationException

    config = Configuration()

    # Skip test if Accelize credentials not available
    if not config.has_accelize_credential():
        pytest.skip('Accelize Credentials required')

    # Test: Invalid AcceleratorClient name
    accelerator = AcceleratorClient('accelerator_not_exists', config=config)
    with pytest.raises(AcceleratorConfigurationException):
        accelerator.get_requirements('OVH')

    # Test: Provider not exists
    accelerator = AcceleratorClient('axonerve_hyperfire', config=config)
    with pytest.raises(AcceleratorConfigurationException):
        accelerator.get_requirements('no_exist_CSP')

    # Test: Everything OK
    name = 'axonerve_hyperfire'
    accelerator = AcceleratorClient(name, config=config)
    response = accelerator.get_requirements('OVH')

    assert response['accelerator'] == name


def test_acceleratorclient_url():
    """Tests AcceleratorClient.url"""
    from acceleratorAPI.client import AcceleratorClient
    from acceleratorAPI.exceptions import AcceleratorConfigurationException

    # Mock some accelerators parts
    class DummyAccelerator(AcceleratorClient):
        """Dummy AcceleratorClient"""
        use_last_configuration_called = False

        def __del__(self):
            """Do nothing"""

        def _check_accelize_credential(self):
            """Don't check credential"""

        def _use_last_configuration(self):
            """Checks if called"""
            self.use_last_configuration_called = True

    accelerator = DummyAccelerator('Dummy')

    # Test: No URL provided
    with pytest.raises(AcceleratorConfigurationException):
        accelerator.url = None

    with pytest.raises(AcceleratorConfigurationException):
        accelerator.url = ''

    # Test: Invalid URL provided
    # Not for test all bad URL cases, only that check_url
    # function is properly called
    with pytest.raises(ValueError):
        accelerator.url = 'http://url_not_valid'

    # Test: Valid URL
    ip_address = '127.0.0.1'
    url = 'http://%s' % ip_address
    accelerator.url = url
    assert accelerator._url == url
    assert accelerator._api_client.configuration.host == url
    assert accelerator.use_last_configuration_called

    # Test: URL set with IP
    accelerator.url = ip_address
    assert accelerator._url == url


def test_acceleratorclient_start():
    """Tests AcceleratorClient.start"""
    from acceleratorAPI.client import AcceleratorClient
    from acceleratorAPI.exceptions import AcceleratorRuntimeException
    import acceleratorAPI.swagger_client as swagger_client

    # Mock Swagger REST API ConfigurationApi
    excepted_parameters = None
    excepted_datafile = None
    configuration_read_in_error = 0

    base_parameters_result = {
        'app': {'status': 0, 'msg': 'dummy_msg'}}

    class ConfigurationApi:
        """Fake swagger_client.ConfigurationApi"""

        def __init__(self, api_client):
            """Store API client"""
            self.api_client = api_client

        @staticmethod
        def configuration_create(parameters, datafile):
            """Checks input arguments and returns fake response"""

            # Check parameters
            if excepted_parameters is not None:
                assert json.loads(parameters) == excepted_parameters
            if excepted_datafile is not None:
                assert datafile == excepted_datafile

            # Return response
            Response = collections.namedtuple(
                'Response', ['url', 'id', 'parametersresult'])

            return Response(
                url='dummy_url', id='dummy_id',
                parametersresult=json.dumps(base_parameters_result))

        @staticmethod
        def configuration_read(id_value):
            """Checks input arguments and returns fake response"""
            Response = collections.namedtuple('Response', ['inerror', 'id', 'url'])

            # Check parameters
            assert id_value == 'dummy_id'

            # Return response
            return Response(url='dummy_url', id=id_value, inerror=configuration_read_in_error)

    # Mock some accelerators parts
    class DummyAccelerator(AcceleratorClient):
        """Dummy AcceleratorClient"""

        def __del__(self):
            """Do nothing"""

        def _check_accelize_credential(self):
            """Don't check credential"""

        @property
        def url(self):
            """Fake URL"""
            return 'dummy_accelerator_url'

    accelerator = DummyAccelerator(
        'Dummy', client_id='dummy_client_id', secret_id='dummy_secret_id')

    base_parameters = {
        "env": {
            "client_id": accelerator.client_id,
            "client_secret": accelerator.secret_id}}

    base_response = {'url_config': 'dummy_url',
                     'url_instance': accelerator.url}

    # Monkey patch Swagger client with mocked API
    swagger_client_configure_api = swagger_client.ConfigurationApi
    swagger_client.ConfigurationApi = ConfigurationApi

    # Tests
    try:
        # Check with arguments
        accelerator_parameters = {'dummy_param': None}
        excepted_parameters = base_parameters.copy()
        excepted_parameters.update(accelerator_parameters)
        excepted_datafile = 'dummy_datafile'
        excepted_response = base_response.copy()
        excepted_response.update(base_parameters_result)

        assert excepted_response == accelerator.start(
            datafile=excepted_datafile,
            accelerator_parameters=accelerator_parameters)

        # Check default values
        excepted_datafile = ''
        excepted_parameters = base_parameters.copy()
        excepted_parameters.update(accelerator._configuration_parameters)
        excepted_response = base_response.copy()
        excepted_response.update(base_parameters_result)

        assert excepted_response == accelerator.start()

        # Check error from host
        configuration_read_in_error = 1
        with pytest.raises(AcceleratorRuntimeException):
            assert excepted_response == accelerator.start()

    # Restore Swagger client API
    finally:
        swagger_client.ConfigurationApi = swagger_client_configure_api


def test_acceleratorclient_use_last_configuration():
    """Tests AcceleratorClient._use_last_configuration"""
    from acceleratorAPI.client import AcceleratorClient
    import acceleratorAPI.swagger_client as swagger_client

    # Mock Swagger REST API ConfigurationApi
    Config = collections.namedtuple('Config', ['url', 'used'])
    config_list = []

    class ConfigurationApi:
        """Fake swagger_client.ConfigurationApi"""

        def __init__(self, api_client):
            """Store API client"""
            self.api_client = api_client

        @staticmethod
        def configuration_list():
            """Returns fake response"""
            Response = collections.namedtuple('Response', ['results'])
            return Response(results=config_list)

    # Mock some accelerators parts
    class DummyAccelerator(AcceleratorClient):
        """Dummy AcceleratorClient"""

        def __del__(self):
            """Do nothing"""

        def _check_accelize_credential(self):
            """Don't check credential"""

    # Monkey patch Swagger client with mocked API
    swagger_client_configure_api = swagger_client.ConfigurationApi
    swagger_client.ConfigurationApi = ConfigurationApi

    # Tests:
    # method called through AcceleratorClient.url, through AcceleratorClient.__init__
    try:

        # No previous configuration
        accelerator = DummyAccelerator('Dummy', url='https://www.accelize.com')
        assert accelerator.configuration_url is None

        # Unused previous configuration
        config_list.append(Config(url='dummy_config_url', used=0))
        accelerator = DummyAccelerator('Dummy', url='https://www.accelize.com')
        assert accelerator.configuration_url is None

        # Used previous configuration
        config_list.insert(0, Config(url='dummy_config_url_2', used=1))
        accelerator = DummyAccelerator('Dummy', url='https://www.accelize.com')
        assert accelerator.configuration_url == 'dummy_config_url_2'

    # Restore Swagger client API
    finally:
        swagger_client.ConfigurationApi = swagger_client_configure_api


def test_acceleratorclient_stop():
    """Tests AcceleratorClient.stop"""
    from acceleratorAPI.client import AcceleratorClient
    from acceleratorAPI.exceptions import AcceleratorRuntimeException
    import acceleratorAPI.swagger_client as swagger_client

    # Mock Swagger REST API StopApi
    is_alive = True
    stop_list = {'app': {'status': 0, 'msg': ''}}

    class StopApi:
        """Fake swagger_client.StopApi"""
        is_running = True

        def __init__(self, api_client):
            """Store API client"""
            self.api_client = api_client

        @classmethod
        def stop_list(cls):
            """Simulates accelerator stop and returns fake response"""
            # Stop AcceleratorClient
            cls.is_running = False

            # Return result
            return stop_list

    # Mock some accelerators parts
    class DummyAccelerator(AcceleratorClient):
        """Dummy AcceleratorClient"""

        def _check_accelize_credential(self):
            """Don't check credential"""

        def is_alive(self):
            """Raise on demand"""
            if not is_alive:
                raise AcceleratorRuntimeException()

    # Monkey patch Swagger client with mocked API
    swagger_client_stop_api = swagger_client.StopApi
    swagger_client.StopApi = StopApi

    # Tests
    try:
        # AcceleratorClient to stop
        assert DummyAccelerator('Dummy').stop() == stop_list
        assert not StopApi.is_running

        # Auto-stops with context manager
        StopApi.is_running = True
        with DummyAccelerator('Dummy') as accelerator:
            # Checks __enter__ returned object
            assert isinstance(accelerator, AcceleratorClient)
        assert not StopApi.is_running

        # Auto-stops on garbage collection
        StopApi.is_running = True
        DummyAccelerator('Dummy')
        gc.collect()
        assert not StopApi.is_running

        # No accelerator to stop
        is_alive = False
        assert DummyAccelerator('Dummy').stop() is None

    # Restore Swagger client API
    finally:
        swagger_client.StopApi = swagger_client_stop_api


def test_acceleratorclient_process_curl():
    """Tests AcceleratorClient._process_curl with PycURL"""
    # Skip if PycURL not available
    try:
        import pycurl
    except ImportError:
        pytest.skip('Pycurl module required')
        return

    # Check PycURL is enabled in accelerator API
    import acceleratorAPI.client
    assert acceleratorAPI.client._USE_PYCURL

    # Start testing
    from acceleratorAPI.client import AcceleratorClient
    from acceleratorAPI.exceptions import AcceleratorRuntimeException

    # Mock some accelerators parts
    class DummyAccelerator(AcceleratorClient):
        """Dummy AcceleratorClient"""

        def _check_accelize_credential(self):
            """Don't check credential"""

        def __del__(self):
            """Does nothing"""

    # Mock PycURL
    pycurl_curl = pycurl.Curl
    perform_raises = False
    api_response = ''

    class Curl:
        """Fake cURL that don"t communicate"""
        mock_write = None

        def __init__(self):
            self.curl = pycurl_curl()

        def perform(self):
            """Don't communicated but write in buffer"""
            # Simulate exception
            if perform_raises:
                raise pycurl.error

            # Write api_response
            self.mock_write(api_response)

        def setopt(self, *args):
            """set cURL options and intercept WRITEFUNCTION"""
            if args[0] == pycurl.WRITEFUNCTION:
                self.mock_write = args[1]
            self.curl.setopt(*args)

        def close(self):
            """Close curl"""
            self.curl.close()

    pycurl.Curl = Curl

    # Tests
    try:
        # Mock some variables
        dummy_parameters = 'dummy_accelerator_parameters'
        dummy_datafile = 'dummy_datafile'

        accelerator = DummyAccelerator('Dummy')
        accelerator._configuration_url = 'dummy_configuration'

        # Test if work as excepted
        expected_response = {'id': 'dummy_id', 'processed': 'dummy_processed'}
        api_response = json.dumps(expected_response)
        response_id, processed = accelerator._process_curl(
            dummy_parameters, dummy_datafile)
        assert response_id == expected_response['id']
        assert processed == expected_response['processed']

        # Test: Invalid response
        api_response = '{id: corrupted_data'
        with pytest.raises(AcceleratorRuntimeException):
            accelerator._process_curl(
                dummy_parameters, dummy_datafile)

        # Test: No id in response
        api_response = '{}'
        with pytest.raises(AcceleratorRuntimeException):
            accelerator._process_curl(
                dummy_parameters, dummy_datafile)

        # Test: Curl.perform raise Exception
        perform_raises = True
        with pytest.raises(AcceleratorRuntimeException):
            accelerator._process_curl(
                dummy_parameters, dummy_datafile)

    # Restore PycURL
    finally:
        pycurl.Curl = pycurl_curl


def test_acceleratorclient_process_swagger():
    """Tests AcceleratorClient._process_swagger with Swagger"""
    # Clean imported modules
    # to force to reimport without PycURL if present
    pycurl_module = sys.modules.get('pycurl')
    if pycurl_module is not None:
        sys.modules['pycurl'] = None
        try:
            del sys.modules['acceleratorAPI.client']
        except KeyError:
            pass
        gc.collect()

    # Check PycURL is disabled in accelerator API
    import acceleratorAPI.client
    assert not acceleratorAPI.client._USE_PYCURL

    # Starts testing with PycURL disabled
    try:
        from acceleratorAPI.client import AcceleratorClient
        import acceleratorAPI.swagger_client as swagger_client

        # Mock some variables
        dummy_id = 'dummy_id'
        dummy_processed = 'dummy_processed'
        dummy_parameters = 'dummy_accelerator_parameters'
        dummy_datafile = 'dummy_datafile'
        dummy_configuration = 'dummy_configuration'

        # Mocks Swagger REST API ProcessApi
        class ProcessApi:
            """Fake swagger_client.ProcessApi"""

            def __init__(self, api_client):
                """Store API client"""
                self.api_client = api_client

            @staticmethod
            def process_create(configuration, parameters, datafile):
                """Checks input arguments and returns fake response"""
                assert parameters == dummy_parameters
                assert datafile == dummy_datafile
                assert configuration == dummy_configuration

                # Return fake response
                Response = collections.namedtuple('Response', ['processed', 'id'])
                return Response(id=dummy_id, processed=dummy_processed)

        # Mock some accelerators parts
        class DummyAccelerator(AcceleratorClient):
            """Dummy AcceleratorClient"""

            def _check_accelize_credential(self):
                """Don't check credential"""

            def __del__(self):
                """Does nothing"""

        # Monkey patch Swagger client with mocked API
        swagger_client_process_api = swagger_client.ProcessApi
        swagger_client.ProcessApi = ProcessApi

        # Tests
        try:
            # Test if work as excepted
            accelerator = DummyAccelerator('Dummy')
            accelerator._configuration_url = dummy_configuration

            response_id, processed = accelerator._process_swagger(
                dummy_parameters, dummy_datafile)
            assert response_id == dummy_id
            assert processed == dummy_processed

        # Restore Swagger API
        finally:
            swagger_client.ProcessApi = swagger_client_process_api

    # Restores PycURL
    finally:
        if pycurl_module is not None:
            sys.modules['pycurl'] = pycurl_module
            try:
                del sys.modules['acceleratorAPI.accelerator']
            except KeyError:
                pass
            gc.collect()


def test_acceleratorclient_process(tmpdir):
    """Tests AcceleratorClient._process"""
    from acceleratorAPI.client import AcceleratorClient
    import acceleratorAPI.exceptions as exc
    import acceleratorAPI._utilities as utl
    import acceleratorAPI.swagger_client as swagger_client

    # Creates temporary output dir and file in
    tmp_dir = tmpdir.dirpath()
    file_in = tmp_dir.join('file_in.txt')
    dir_out = tmp_dir.join('subdir')
    file_out = dir_out.join('file_out.txt')

    # Mocks some variables
    processed = False
    in_error = True
    parameters_result = {'app': {
        'status': 0, 'msg': 'dummy_parameters_result'}}
    datafile_result = {'app': {
        'status': 0, 'msg': 'dummy_datafile_result'}}
    out_content = b'file out content'

    # Mocks Swagger REST API ProcessApi
    class ProcessApi:
        """Fake swagger_client.ProcessApi"""

        def __init__(self, api_client):
            """Store API client"""
            self.api_client = api_client

        @staticmethod
        def process_read(id_value):
            """Checks input arguments and returns fake response"""
            Response = collections.namedtuple(
                'Response', ['processed', 'inerror',
                             'parametersresult', 'datafileresult'])

            # Check parameters
            assert id_value == 'dummy_id'

            # Returns response
            return Response(
                processed=True, inerror=in_error,
                parametersresult=json.dumps(parameters_result),
                datafileresult=json.dumps(datafile_result))

        @staticmethod
        def process_delete(id_value):
            """Checks input arguments"""
            # Check parameters
            assert id_value == 'dummy_id'

    # Mock some accelerators parts
    class DummyAccelerator(AcceleratorClient):
        """Dummy AcceleratorClient"""

        def _process_swagger(self, accelerator_parameters, datafile):
            """Mocks process function (tested separately)

            Checks input arguments and returns fake response"""
            # Checks input parameters
            assert json.loads(accelerator_parameters) == self._process_parameters
            assert datafile == file_in

            # Returns fake result
            return 'dummy_id', processed

        _process_curl = _process_swagger

        def _check_accelize_credential(self):
            """Don't check credential"""

        def __del__(self):
            """Does nothing"""

    # Mocks requests in utilities
    class DummySession:
        """Fake requests.Session"""

        @staticmethod
        def get(datafile_result_arg, **_):
            """Checks input arguments and returns fake response"""
            Response = collections.namedtuple('Response', ['raw'])

            # Checks input parameters
            assert json.loads(datafile_result_arg) == datafile_result

            # Returns fake response
            return Response(raw=io.BytesIO(out_content))

    # Monkey patch Swagger client with mocked API
    swagger_client_process_api = swagger_client.ProcessApi
    swagger_client.ProcessApi = ProcessApi

    # Monkey patch requests in utilities
    utl_http_session = utl.http_session
    utl.http_session = DummySession

    # Tests
    try:
        # Test accelerator not configured
        accelerator = DummyAccelerator('Dummy')
        with pytest.raises(exc.AcceleratorConfigurationException):
            accelerator.process(str(file_in), str(file_out))

        accelerator._configuration_url = 'dummy_configuration'

        # Test input file not exists
        with pytest.raises(OSError):
            accelerator.process(str(file_in), str(file_out))

        # Creates input file
        file_in.write('file in content')
        assert file_in.check(file=True)

        # Test result "inerror" and output-dir creation
        assert not dir_out.check(dir=True)

        with pytest.raises(exc.AcceleratorRuntimeException):
            accelerator.process(str(file_in), str(file_out))

        assert dir_out.check(dir=True)

        # Sets to not in error
        in_error = False

        # Check if working as excepted
        assert accelerator.process(str(file_in), str(file_out)) == parameters_result
        assert file_out.read_binary() == out_content

    # Restore requests and swagger API
    finally:
        utl.http_session = utl_http_session
        swagger_client.ProcessApi = swagger_client_process_api