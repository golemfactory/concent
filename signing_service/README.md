# signing-service

Stand-alone Python application used for signing Ethereum transactions received via MiddleMan protocol.


### Install

You can install this library:

``` bash
python setup.py install
```


### Install for development

You can install this library for development:

``` bash
python setup.py develop
```


### Running tests

You can run automated tests from the same  with:

``` bash
python -m pytest -p no:django .
```


### Running

To run SigningService you need the following:

- Address and port of a Middleman service on a Concent cluster to which SigningService wants to connect to.
  If port is omitted, `9055` is used by default.
- A private key for signing sent messages.
- Concent's public key for verifying signatures of received messages.
- Ethereum private key for signing Ethereum transactions.
- [Sentry DNS](https://docs.sentry.io/quickstart/#configure-the-dsn) if you want to submit error reports to a
- Sentry instance (optional but recommended).
    - You may also want to submit reports to the different instances used by Concent (recommended).
      To do so, please use `--sentry-environment` option to set the `environment` tag depending on which cluster you're connecting to.
      Available options are `concent-staging`, `concent-testnet` or `concent-mainnet`.
      If you're submitting to any other instance, you can set this tag to anything you want or even simply omit it.
      Its only purpose is to let us discern reports from different environments in Sentry.
