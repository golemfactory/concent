# concent
Repository for Concent Service sources

## Configuration

### `local_settings.py``

All the configuration of the application is defined in `concent_api/concent_api/settings/`.
When setting up a new instance you should create a `local_settings.py` file in that directory and import the default production settings:

``` python
from .production import *
```

Now you can add any settings you need or override defaults defined in `base.py` and `production.py`.
