from pytest import fixture
from keywords import nova_helper, vm_helper, cinder_helper


@fixture(scope='function', autouse=True)
def delete_resources_func(request):
    def delete_():
        ResourceCleanup._delete(ResourceCleanup._get_resources('function'))
        ResourceCleanup._reset('function')
    request.addfinalizer(delete_)


@fixture(scope='class', autouse=True)
def delete_resources_class(request):
    def delete_():
        ResourceCleanup._delete(ResourceCleanup._get_resources('class'))
        ResourceCleanup._reset('class')
    request.addfinalizer(delete_)


@fixture(scope='module', autouse=True)
def delete_resources_module(request):
    def delete_():
        ResourceCleanup._delete(ResourceCleanup._get_resources('module'))
        ResourceCleanup._reset('module')
    request.addfinalizer(delete_)


class ResourceCleanup:
    __resources_to_cleanup = {
        'function': {
            'vms': [],
            'volumes': [],
            'flavors': [],
        },
        'class': {
            'vms': [],
            'volumes': [],
            'flavors': [],
        },
        'module': {
            'vms': [],
            'volumes': [],
            'flavors': [],
        }
    }

    @classmethod
    def _get_resources(cls, scope):
        return cls.__resources_to_cleanup[scope]

    #
    # @fixture(scope='function', autouse=False)
    # def delete_resources_func(self, request):
    #     def delete_():
    #         self.__delete_resources(self.__resources_to_cleanup['function'])
    #     request.addfinalizer(delete_)
    #
    # @fixture(scope='class', autouse=False)
    # def delete_resources_class(self, request):
    #     def delete_():
    #         self.__delete_resources(self.__resources_to_cleanup['class'])
    #     request.addfinalizer(delete_)
    #
    # @fixture(scope='module', autouse=False)
    # def delete_resources_module(self, request):
    #     def delete_():
    #         self.__delete_resources(self.__resources_to_cleanup['module'])
    #     request.addfinalizer(delete_)

    @staticmethod
    def _delete(resources):
        vms = resources['vms']
        volumes = resources['volumes']
        flavors = resources['flavors']
        if vms:
            vm_helper.delete_vms(vms)
        if volumes:
            cinder_helper.delete_volumes(volumes)
        if flavors:
            nova_helper.delete_flavors(flavors)

    @classmethod
    def _reset(cls, scope):
        cls.__resources_to_cleanup[scope] = {
            'vms': [],
            'volumes': [],
            'flavors': [],
        }

    @classmethod
    def add(cls, resource_type, resource_id, scope='function'):
        """
        Add resource to cleanup list.

        Args:
            resource_type (str): one of these: 'vm', 'volume', 'flavor
            resource_id (str): id of the resource to add to cleanup list
            scope (str): when the cleanup should be done. Valid value is one of these: 'function', 'class', 'module'

        """
        scope == scope.lower()
        resource_type = resource_type.lower()
        valid_scopes = ['function', 'class', 'module']
        valid_types = ['vm', 'volume', 'flavor']
        if scope not in valid_scopes:
            raise ValueError("'scope' param value has to be one of the: {}".format(valid_scopes))
        if resource_type not in valid_types:
            raise ValueError("'resouce_type' param value has to be one of the: {}".format(valid_types))

        key = resource_type + 's'
        cls.__resources_to_cleanup[scope][key].append(resource_id)
