# coding=utf-8
"""apyfal.storage.oss tests"""

import pytest
from tests.test_storage_bucket import run_full_real_test_sequence, import_from_generic_test


def test_ossclass_import():
    """OSSStorage import"""
    # Test: Import by factory without errors
    import_from_generic_test('OSS')


def test_exception_handler():
    """Test _exception_handler"""
    from oss2.exceptions import OssError
    import apyfal.exceptions as exc
    from apyfal.storage.oss import _exception_handler

    kwargs = dict(
        headers={}, body='',
        details={'Code': 'ErrorCode', 'Message': 'Message'})

    # Tests not raise
    with _exception_handler():
        assert True

    # Tests 404
    with pytest.raises(exc.StorageResourceNotExistsException):
        with _exception_handler():
            raise OssError(status=404, **kwargs)

    # Tests 403
    with pytest.raises(exc.StorageAuthenticationException):
        with _exception_handler():
            raise OssError(status=403, **kwargs)

    # Tests others
    with pytest.raises(exc.StorageRuntimeException):
        with _exception_handler():
            raise OssError(status=500, **kwargs)


@pytest.mark.need_csp
@pytest.mark.need_csp_alibaba
def test_ossclass_real(tmpdir):
    """OSSStorage in real case"""
    run_full_real_test_sequence('OSS', tmpdir)