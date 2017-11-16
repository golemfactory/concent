# concent
Repository for Concent Service sources

## Configuration

### `local_settings.py`

All the configuration of the application is defined in `concent_api/concent_api/settings/`.
When setting up a new instance you should create a `local_settings.py` file in that directory and import the default production settings:

``` python
from .production import *
```

Now you can add any settings you need or override defaults defined in `base.py` and `production.py`.

### Generating public and private key pair for settings

Keys should be generated using the `ECCx` class from `golem-messages`:

``` python
from golem_messages import ECCx

ecc = ECCx(None)

print("CONCENT_PUBLIC_KEY  = {}".format(ecc.raw_pubkey))
print("CONCENT_PRIVATE_KEY = {}".format(ecc.raw_privkey))
```

You can put the output of the script above directly in your `local_settings.py`
