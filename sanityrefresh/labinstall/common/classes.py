class Host(object):
    def __init__(self, *initial_data, **kwargs):
        for dictionary in initial_data:
            for key in dictionary:
                setattr(self, key, dictionary[key])
        for key in kwargs:
            setattr(self, key, kwargs[key])

    def __str__(self):
        return str(vars(self))

class Controller(Host):

    def  __init__(*initial_data, **kwargs):
        super().__init__(*initial_data, **kwargs)
        
