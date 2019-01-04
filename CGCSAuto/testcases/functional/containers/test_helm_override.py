from keywords import container_helper


def test_helm_override_update_and_reset():
    new_conf = 'conf.nova.DEFAULT.foo=bar'
    conf_path = '/etc/nova/nova.conf'

    container_helper.update_helm_override(chart='nova', namespace='openstack',
                                          kv_pairs={'conf.nova.DEFAULT.foo': 'bar'})

    fields = ('combined_overrides', 'system_overrides', 'user_overrides')
    combined_overrides, system_overrides, user_overrides = \
        container_helper.get_helm_override_info(chart='nova', namespace='openstack', fields=fields)

    assert 'bar' == user_overrides['conf']['nova']['DEFAULT'].get('foo'), \
        "{} is not shown in user overrides".format(new_conf)
    assert 'bar' == combined_overrides['conf']['nova']['DEFAULT'].get('foo'), \
        "{} is not shown in combined overrides".format(new_conf)
    assert not system_overrides['conf']['nova']['DEFAULT'].get('foo'), \
        "User override {} listed in system overrides unexpectedly".format(new_conf)


