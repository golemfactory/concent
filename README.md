# concent
Repository for Concent Service sources

## Production setup

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

## Development setup

### Preparing your environment for development

1. Install [Python](https://www.python.org/) >= 3.6 using your package manager.

2. Install [PostgreSQL](https://www.postgresql.org) >= 10 using your package manager.

    If you're using this machine only for development, configure PosgreSQL to be reachable only from `localhost`.

    Make sure that PostgreSQL service is running (in many distros the service is started automatically right after installation).

3. Clone this repository

    ``` bash
    git clone git@github.com:golemfactory/concent.git
    ```

4. Install dependencies in a virtualenv

    ``` bash
    virtualenv ~/.virtualenvs/concent --python python3
    source ~/.virtualenvs/concent/bin/activate
    pip install pip --upgrade

    # Dependencies for running concent
    pip install --requirement concent_api/requirements.lock

    # Extra stuff for development that's not normally installed in production. Linter, debugger, etc.
    pip install --requirement requirements-development.txt

    # All dependencies needed for developers. Concent, Singing Service, Middleman Protocol and requirements placed in requirements-development.txt
    ./install-development-requirements.sh
    ```

    **libsecp256k1**

    If `pip` tries to build a Python package called [secp256k1](https://github.com/ludbb/secp256k1-py) and fails, you'll need to install a Linux package called [libsecp256k1](https://github.com/bitcoin-core/secp256k1) using your package manager and rerun the installation.
    This should not be the case most of the time because there are binary .wheels available on PyPI and they have this library bundled with them.
    They don't cover all possible configurations though.
    If you're running a very recent version of Python, `pip` might not be able to find pre-built binaries matching your version of the interpreter and try to build the C extension on its own.
    This will only succeed if you have `libsecp256k1` installed.
    The package is available in the repositories of some Linux distributions.
    If you can't find it in your distro, you can also build it manually from source by following the instructions listed on the page linked above.

    **OpenSSL 1.1**

    [golem-messages](https://github.com/golemfactory/golem-messages) depends on [pyelliptic](https://github.com/yann2192/pyelliptic) which is not compatible with OpenSSL 1.1.
    For it to work you'll have to install OpenSSL 1.0.
    Fortunately most distributions still provide both versions.
    For example on Debian you can install `libssl1.0.2` and `libssl1.0-dev`.
    On Arch Linux there's `openssl-1.0`.

    You'll run into a problem if you have both OpenSSL 1.0 and OpenSSL 1.1 installed at the same time though.
    `pyelliptic` calls `ctypes.util.find_library('crypto')` to load the library and if you have both versions it loads version 1.1.
    To prevent this you can patch its source and hard-code the path to OpenSSL 1.0:

    ``` bash
    sed \
        "s%ctypes.util.find_library('crypto')%'/usr/lib/openssl-1.0/libcrypto.so'%" \
        -i ~/.virtualenvs/concent/lib/python3.*/site-packages/pyelliptic/openssl.py
    ```

    Note that the path to `libcrypto.so` can vary between distributions.
    On Debian it's `/usr/lib/x86_64-linux-gnu/libcrypto.so.1.0`.
    On Arch Linux you'll find it in `/usr/lib/openssl-1.0/libcrypto.so`.
    You'll have to adjust the command above to match your system.

5. Create your local configutation in `concent_api/concent_api/settings/local_settings.py`:

    ``` python
    from .development import *
    ```

    If your database configuration differs from the defaults, you may need to tweak the values below and add them to your `local_settings.py` too:

    ``` python
    DATABASES['NAME']     = 'concent_api'
    DATABASES['USER']     = 'postgres'
    DATABASES['PASSWORD'] = ''
    DATABASES['HOST']     = '5432'
    DATABASES['PORT']     = 'locslhost'
    ```

6. Create an empty database with the name you set in `DATABASES['NAME']` (`concent_api` if you did not set it explicitly):

    ``` bash
    createdb --username postgres concent_api
    ```

7. Run Django migrations for each database to initialize and create the tables:

    ```
    concent_api/manage.py migrate --database control
    concent_api/manage.py migrate --database storage
    ```

8. Create a superuser account:

    ```
    concent_api/manage.py createsuperuser --database control
    ```
    
9. Enable time synchronization:

    Concent is highly time dependent service. Thus time synchronization should be enabled:
    ```bash
    timedatectl set-ntp true
    ```

### Running concent in development

To start a Concent server simply run

``` bash
concent_api/manage.py runserver
```

The server is now reachable at http://localhost:8000/.

Note that Concent does not have a UI so you will only get HTTP 404 if you try to go to that address in the browser.
You can access the admin panel at http://localhost:8000/admin/ but this is only for maintenance and accessing statistics.

The primary way to interact with the service is via a Golem client.
You can simulate this interaction with a tool like [curl](https://curl.haxx.se/) or custom scripts that send HTTP requests.
One of such scripts, meant to test a working Concent server in a very rudimentary way is `api-test.py`:

``` bash
concent_api/api-test.py http://localhost:8000
```

### Running tests

You can run automated tests, code analysis and Django configuration checks with:

``` bash
./full_check.sh
```

Always run this command before submitting code in a pull request and make sure that there are no warnings or failed tests.


### Running Middleman

Concent signs Ethereum transactions by passing them to an external signing service provided by Golem.
To decrease the attack surface the service is not serving any requests.
Instead, Concent runs a component that opens a TCP port, and allows the signing service to connect at will.
This component (internally called "Middleman") needs to be started separately from the main server:

``` bash
concent_api/manage.py middleman
```

The command should work fine without any extra arguments.
You can use `--help` option to see all the available options.

Note that in development you need to run an instance of the Signing Service yourself.
The application is maintained by the Concent team as well and you can find it in this repository.
See [Signing Service README](signing_service/README.md)

### Running Celery workers in development

Concent uses Celery asynchronous task queue to perform additional verification for Golem clients.
Concent works fine without them, they are required only if you want to perform additional verification use case.
To use workers you should have a message broker like RabbitMQ or Redis running locally.

You can run Celery workers for Concent with:

``` bash
concent_api/celery worker --app concent_api --loglevel info --queues concent,conductor,verifier
```

### Deploying GNTDeposit contract

To be able to run end-to-end (E2E) tests locally without interfering with other Concent instances, you need a separate instance of the `GNTDeposit` contract on the blockchain and a separate Ethereum account Concent will use to issue transactions and transfer deposits.
Concent assumes that it's the only entity with access to the deposits and you'll get false positives and random failures if that's not true.

1. Get [GNTDeposit.sol](https://github.com/golemfactory/golem-contracts/blob/master/contracts/GNTDeposit.sol)
from [golem-contracts](https://github.com/golemfactory/golem-contracts) repository.

2. Fallow this tutorial to deploy GNTDeposit.sol on `rinkeby` ethereum testnet:
[Deploy Smart Contracts on Ropsten Testnet through Ethereum Remix](https://medium.com/swlh/deploy-smart-contracts-on-ropsten-testnet-through-ethereum-remix-233cd1494b4b)

    It involves installing `MetaMask` in your browser, importing ethereum account that you generate before using
    hex-encoded value and getting some testnet ETH. Then copy `GNTDeposit.sol` with all dependencies to single file in
    solidity IDE - `remix`. You can use [solidity-flattener](https://github.com/BlockCatIO/solidity-flattener) to do so.

3. There are four variables needed to deploy new GNTDeposit contract:

    - `_token` - GNTB contract address.
    For all testnet environments, it should be hardcoded to `0x123438d379BAbD07134d1d4d7dFa0BCbd56ca3F3`.

    - `_concent` - Concent ethereum address, compatible with keys pair generated before.

    - `_coldwallet` - Another or the same concent ethereum address. It's used as an account to store communication and
    verification fees.

    - `_withdrawal_delay` - This is the time(in seconds) after which a Golem client is allowed to withdraw its deposit.
    We used mainnet value so far, which is 48h (172800 seconds).

4. After successfully deploying your own copy of `GNTDeposit` contract, you need to put the new values in your `local_settings.py`:

    - `GNT_DEPOSIT_CONTRACT_ADDRESS`: the Ethereum address of the newly deployed contract
    - `CONCENT_ETHEREUM_PRIVATE_KEY`: the private key matching contract's address (binary value as Python's `bytes`)
    - `CONCENT_ETHEREUM_PUBLIC_KEY`: the public key matching contract's address (hex-encoded value as Python's `str`)
    - `CONCENT_PRIVATE_KEY`: the same as `CONCENT_ETHEREUM_PRIVATE_KEY`
    - `CONCENT_PUBLIC_KEY`: the same as `CONCENT_ETHEREUM_PUBLIC_KEY`, but in binary value

5. For the tests to work there must be some test GNT on deposit accounts belonging to the provider and requestor that interact with Concent in E2E tests.
You need to manually request some GNT from the faucet and transfer it to the accounts.
Before doing this, remember to clear Concent's databases if there were any previous transaction being made with different `GNT_DEPOSIT_CONTRACT_ADDRESS`.
Then adjust the code below to your need and type it in the Django shell (`manage.py shell`):

    ``` python
    from core.payments.payment_interface import PaymentInterface

    p = PaymentInterface()  # eth address for "p" depends on `CONCENT_ETHEREUM_PRIVATE_KEY` and `CONCENT_ETHEREUM_PUBLIC_KEY`
    p.request_gnt_from_faucet()
    # check if You have GNT with `p.get_gnt_balance(p.get_eth_address())`

    p.open_gate()
    # check if the command above worked with `p.get_gate_address()` (should return eth address)

    p.transfer_gnt(p.get_gate_address(), value)  # `value` is amount of GNT You want to convert to GNTB
    p.transfer_from_gate()
    # check if You have GNTB with `p.get_gntb_balance(p.get_eth_address())`

    p.deposit_payment(value)  # value is amount of GNTB You want to use as deposit
    # check if You have deposit with `p.get_deposit_value(p.get_eth_address())`
    ```
