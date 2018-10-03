## Bankster (with deposit claim tracking)

Bankster is an intermediate layer between Concent Core and the Ethereum client (Geth).
All communication with the Ethereum client is performed via Golem's Smart Contracts Interface (SCI) which is used as a library.

### Components and communication
![bankster-components](https://user-images.githubusercontent.com/137030/41231712-4e124bfa-6d84-11e8-8be2-3f085ff1d3dc.png)

### API

#### `POST bankster/claim-deposit/` endpoint
- **Input format**: JSON
- **Output format**: JSON

The purpose of this endpoint is to check whether the clients participating in a use case have enough funds in their deposits to cover all the costs associated with the use case in the pessimistic scenario and to mark those funds as locked until they get paid out.

Concent core communicates with this endpoint at the beginning of any use case that may require payment from deposit within a single subtask.
Currently those are `ForcedAcceptance` and `AdditionalVerification`.
`ForcedPayment` use case operates on more than one subtask and for that reason requires a separate endpoint.

The funds are locked in anticipation of a future payment but it does not necessarily mean that exactly that amount will be paid out or even that it will actually be paid.
The actual amount paid will depend on the outcome of the use case.

##### Input
| Parameter                       | Type                  | Optional | Remarks                                                                                                                 |
|---------------------------------|-----------------------|----------|-------------------------------------------------------------------------------------------------------------------------|
| `subtask_id`                    | string                | no       | ID of the subtask.
| `concent_use_case`              | `ConcentUseCase`      | no       | Use case in which Concent claims the deposit.
| `requestor_public_key`          | string                | no       | Public key of the requestor. Comes from `TaskToCompute`.
| `provider_public_key`           | string                | no       | Public key of the provider. Comes from `TaskToCompute`.
| `requestor_ethereum_public_key` | string                | no       | Address of the Ethereum account belonging to the requestor. Cannot be the same as `provider_ethereum_public_key`. Comes from `TaskToCompute`.
| `provider_ethereum_public_key`  | string                | no       | Address of the Ethereum account belonging to the provider. Cannot be the same as `requestor_ethereum_public_key`. Comes from `TaskToCompute`.
| `subtask_cost`                  | decimal               | no       | The cost of performing the work on the subtask that the requestor has agreed to pay the provider. Comes from `TaskToCompute.price` multiplied by maximum task duration. Must be greater than zero.

##### Output
| Parameter                       | Type                  | Optional | Remarks                                                                                                                 |
|---------------------------------|-----------------------|----------|-------------------------------------------------------------------------------------------------------------------------|
| `claim_against_requestor`       | int                   | no       | The database ID of the `DepositClaim` object that was created to lock a part of requestor's deposit.
| `claim_against_provider`        | int                   | yes      | The database ID of the `DepositClaim` object that was created to lock a part of provider's deposit. May be empty if nothing is claimed from the provider.

##### Sequence of operation
1. **Claim calculation**: Bankster determines the amount that needs to be claimed from each account:
    - In `ForcedAcceptance` use case:
        - Requestor may have to pay `subtask_cost`.
        - Provider does not pay anything.
    - In `AdditionalVerification` use case:
        - Requestor may have to pay `subtask_cost`.
        - Provider needs to pay verification cost (which is constant and determined by Concent's settings).
2. **Initialization**:
    - Bankster creates `Client` and `DepositAccount` objects (if they don't exist yet) for the requestor and also for the provider if there's a non-zero claim against his account.
        - The transaction is committed at this point to prevent these objects from being rolled back in case of failure.
3. **Deposit query**:
    - Bankster asks SCI about the amount of funds available in requestor's deposit.
    - If the amount claimed from provider's deposit is non-zero, Bankster asks SCI about the amount of funds available in his deposit.
4. **Claim freeze**:
    - Bankster puts a database locks on all `DepositAccount` objects that will be used as payers in newly created `DatabaseClaim`s.
        - If the objects are already locked, waits and retries a few times and eventually fails.
    - The freeze is done after the deposit check to avoid holding the lock for too long.
        Deposit check requires one or more HTTP requests and is a relatively slow operation.
5. **Requestor's spare deposit check**:
    - Bankster sums the `amount`s of all existing `DepositClaim`s where the requestor is the payer.
    - **Claims against requestor's deposit can be paid partially** because the service has already been performed by the provider and giving him something is better than giving nothing.
        If the existing claims against requestor's deposit are greater or equal to his current deposit, we can't add a new claim.
        - Bankster responds with `claim_against_requestor` and `claim_against_requestor` being both `None`.
    - Otherwise Bankster continues.
6. **Provider's spare deposit check**: If the amount claimed from his deposit is non-zero.
    - Bankster sums the `amount`s of all existing `DepositClaim`s where the provider is the payer.
    - **Claims against provider's deposit must be paid in full** because they're payments for using Concent and we did not perform the service yet so we can just refuse.
      If the total of existing claims **and** the current claim is greater or equal to the current deposit, we can't add a new claim.
        - Bankster removes the `DepositClaim` just created aginst requestor's deposit.
        - Bankster responds with `claim_against_requestor` and `claim_against_requestor` being both `None`.
    - Otherwise Bankster continues.
7. **Deposit lock**: For both provider and requestor, if the amount claimed from the deposit is non-zero:
    - Bankster creates a `DepositClaim` object
        - `payee_ethereum_public_key`: payee can be either the provider (if the requestor is the payer) or Concent (if the provider is the payer).
            The address of Concent's account either comes from settings or is automatically inserted by the contract.
        - `amount`: The full amount claimed.
            Even if there's not enough deposit, we don't reduce the claim until the moment when we actually create a transaction.
            The situation may change in the meantime - some claims may be canceled or the client may increase (or reduce) the deposit.
        - `tx_hash`: We're not creating a transaction yet so this field is left empty.
8. **Unfreeze and response**: If everything goes well, Bankster sends a HTTP 200 response.
    - IDs of all the created `DepositClaim`s are included in the response.
        At least one claim must have been created.
    - Database locks on `EthereumAccount`s are released.

##### Expected Concent Core behavior
- Concent Core contacts this endpoint at the beginning of a use case, after validating client's message and determining that the service can be performed.
- Concent Core can access `DepositClaim` objects created by Bankster.
- Concent Core is responsible for removing `DepositClaim` objects if it fails at any point after receiving a positive response from Bankster.
    - Bankster removes `DepositClaim` objects only after they're successfully paid for.
- Concent Core is responsible for removing `DepositClaim` objects if the outcome of the use case indicates that they don't need to be paid (e.g. if additional verification confirms requestor's decision to reject the result).
- `Client` and `DepositAccount` objects are never removed.
    They stay in the database even if the operation fails and even after all the `DepositClaim`s that refer to them are removed.

#### `POST bankster/finalize-payments/` endpoint
- **Input format**: JSON
- **Output format**: JSON

This endpoint tells Bankster to either pay out claimed funds or discard the claims.

Concent Core communicates with this endpoint at the end of any use case that may require payment from deposit within a single subtask.
Currently those are `ForcedAcceptance` and `AdditionalVerification`.
`ForcedPayment` use case operates on more than one subtask and for that reason requires a separate endpoint.

Claims for which the disposition is not to pay are simply discarded, freeing the funds.
This may happen for example when verification confirms requestor's claim and he's freed from the responsibility of covering computation cost.
Note that the provider still has to pay Concent for additional verification in that case.

For each claim for which the disposition says to pay it, Bankster uses SCI to submit an Ethereum transaction to the Ethereum client which then propagates it to the rest of the network.
Hopefully the transaction is included in one of the upcoming blocks on the blockchain.
Bankster updates `DepositClaim` with the transaction ID and starts listening for blockchain events.
The claim is removed from the database once the transaction actually appears on the blockchain.

If there's not enough funds at the moment, the `amount` is decreased.
If there's nothing at all, the claim is discarded without payment.

##### Input
| Parameter                     | Type                              | Optional | Remarks                                                                                                                 |
|-------------------------------|-----------------------------------|----------|-------------------------------------------------------------------------------------------------------------------------|
| deposit_claim_dispositions    | list of `DepositClaimDisposition` | no       |

###### `DepositClaimDisposition`
| Field                         | Type                              | Optional | Remarks                                                                                                                 |
|-------------------------------|-----------------------------------|----------|-------------------------------------------------------------------------------------------------------------------------|
| `deposit_claim`               | int                               | no       | ID of a `DepositClaim` object.
| `pay`                         | bool                              | no       | `True` if the claim should actually be paid. `False` if it should be discarded.

##### Output
| Parameter                     | Type                              | Optional | Remarks                                                                                                                 |
|-------------------------------|-----------------------------------|----------|-------------------------------------------------------------------------------------------------------------------------|
| `success`                     | dict of (int, bool)               | no       | A dict indicating for each `DepositClaim` whether the transaction has been successfully submitted.

##### Sequence of operation
This is performed in a loop, separately for each `DepositClaimDisposition`.

1. **Deposit query**
    - If `pay` is `True`:
        - Bankster asks SCI about the amount of funds available on the deposit account listed in the `DepositClaim`.
2. **Claim freeze**:
    - If the `DepositAccount` belonging to the payer is locked, Bankster waits, retries a few times and eventually fails.
    - Otherwise Bankster puts a database lock on the `DepositAccount` object.
3. **Claim cancellation**:
    - If `pay` is `False`:
        - Bankster simply removes the `DepositClaim` object.
4. **Payment calculation**:
    - If `pay` is `True`:
        - Bankster sums the `amount`s of all existing `DepositClaim`s that have the same payer as the one being processed.
        - Bankster subtracts that value from the amount of funds available in the deposit.
        - If the result is negative or zero, Bankster removes the `DepositClaim` object being processed.
        - Otherwise if the result is lower than `DepositAccount.amount`, Bankster sets this field to the amount that's actually available.
5. **Transaction**:
    - If the `DepositClaim` still exists at this point:
        - Bankster uses SCI to create an Ethereum transaction.
        - Bankster puts transaction ID in `DepositClaim.tx_hash`.
6. **Unfreeze**:
    - Bankster releases the lock on `DepositAccount`.

The database transaction is committed after processing each disposition.
An exception during the processing should release the lock and roll back the changes related to the current disposition but all the previous ones should stay in the database.

After processing all the dispositions or encountering an exception, Bankster prepares the response.

7. **Response**:
    - `success` dict has a key for each claim included in `deposit_claim_dispositions`.
        The value is `True` if and only if Banker actually started processing the corresponding disposition and finished it without errors.

##### Expected Concent Core behavior
- Concent Core contacts this endpoint at the end of a use case, when the service has already been performed and it is known that a payment is necessary.
- Concent Core can access `DepositClaim` objects created by Bankster.

#### `POST bankster/settle-overdue-acceptances/` endpoint
- **Input format**: JSON
- **Output format**: JSON

The purpose of this endpoint is to calculate the total amount that the requestor owes provider for completed computations and transfer that amount from requestor's deposit.
Concent Core is responsible for validating provider's claims and Bankster only calculates and executes the payment.

The provider proves to Concent that the computations were performed and accepted and Concent Core asks Bankster to compare the total value with the amount actually paid by the requestor, either directly or from deposit.
If it turns out that the total value of provider's claims was not covered completely, Concent transfers the missing amount from requestor's deposit.
If the deposit is not large enough to cover the whole amount, Concent transfers as much as possible.
After this operation the provider can no longer claim any other overdue payments that happened before the deposit transfer.

##### Input
| Parameter                       | Type                        | Optional | Remarks                                                                                                                 |
|---------------------------------|-----------------------------|----------|-------------------------------------------------------------------------------------------------------------------------|
| `requestor_public_key`          | string                      | no       | Public key of the requestor. Comes from `TaskToCompute`.
| `provider_public_key`           | string                      | no       | Public key of the provider. Comes from `TaskToCompute`.
| `requestor_ethereum_public_key` | string                      | no       | Address of the Ethereum account belonging to the requestor. Cannot be the same as `provider_ethereum_public_key`. Comes from `TaskToCompute`.
| `provider_ethereum_public_key`  | string                      | no       | Address of the Ethereum account belonging to the provider. Cannot be the same as `requestor_ethereum_public_key`. Comes from `TaskToCompute`.
| `acceptances`                   | list of `SubtaskAcceptance` | no       | List of dicts describing each acceptance. The list must contain at least one object.

###### `SubtaskAcceptance`
| Field                           | Type                        | Optional | Remarks                                                                                                                 |
|---------------------------------|-----------------------------|----------|-------------------------------------------------------------------------------------------------------------------------|
| `subtask_id`                    | string                      | no       | ID of the subtask.
| `payment_ts`                    | timestamp                   | no       | `payment_ts` timestamp from the acceptance message.
| `amount`                        | decimal                     | no       | Amount to be paid.

##### Output
| Parameter                       | Type                        | Optional | Remarks                                                                                                                 |
|---------------------------------|-----------------------------|----------|-------------------------------------------------------------------------------------------------------------------------|
| `claim_against_requestor`       | int                         | yes      | The database ID of the `DepositClaim` object that was created to lock a part of requestor's deposit. If this is empty, the requestor either has no deposit or the deposit is completely covered by existing claims.

##### Sequence of operation
1. **Initialization**:
    - Bankster creates `Client` and `DepositAccount` objects for the requestor if they don't exist yet.
        - The transaction is committed at this point to prevent these objects from being rolled back in case of failure.
2. **Deposit query**:
    - Bankster asks SCI about the amount of funds available in requestor's deposit.
3. **Claim freeze**:
    - If the `DepositAccount` belonging to the requestor is locked, Bankster waits, retries a few times and eventually fails.
    - Otherwise Bankster puts a database lock on the `DepositAccount` object.
4. **Requestor's spare deposit check**:
    - Bankster sums the `amount`s of all existing `DepositClaim`s where the requestor is the payer.
    - If the existing claims against requestor's deposit are greater or equal to his current deposit, we can't add a new claim.
        - Bankster responds with `claim_against_requestor` being `None`.
    - Otherwise Bankster continues.
5. **Claim calculation**:
    - Bankster sums up the amount specified in acceptances.
    - Bankster asks SCI for the list of all relevant payments listed on the blockchain (both normal payments performed by the requestor and forced payments performed by Concent).
    - Bankster computes the amount that is still owed to the provider.
    - Bankster compares the amount with the available deposit minus the existing claims against requestor's account.
        - If the whole amount can't be paid, Concent lowers it to pay as much as possible.
        - The final amount must be non-zero - spare deposit check prevents this.
6. **Transaction**:
    - Bankster uses SCI to create an Ethereum transaction.
7. **Deposit lock**:
    - Bankster creates a `DepositClaim` object
        - `subtask_id` is empty since the claim may refer to multiple subtasks.
        - `amount`: The amount actually used in the transaction.
8. **Unfreeze and response**: If everything goes well, Bankster sends a HTTP 200 response.
    - ID of the created `DepositClaim` is included in the response.
    - Database locks on `EthereumAccount`s are released.

### Database

#### `DepositClaim` model
- **Database**: `control`

| Column name                     | Type                  | Optional | Remarks                                                                                                                 |
|---------------------------------|-----------------------|----------|-------------------------------------------------------------------------------------------------------------------------|
| `subtask_id`                    | string                | yes      | ID of the subtask. It's not a foreign key to `Subtask` because in some use cases (e.g. payment use case) we do not store the subtask details. Can be `NULL` if and only if `concent_use_case` is `ForcedPayment`.
| `payer_deposit_account`         | `DepositAccount`      | no       | The deposit account belonging to the client who is supposed to pay the claim. `payer_deposit_account.ethereum_public_key` cannot be the same as `payee_ethereum_public_key`.
| `payee_ethereum_public_key`     | string                | no       | Address of the Ethereum account belonging to the entity (requestor, provider or Concent) who is supposed to receive the claim. Cannot be the same as `payer_deposit_account.ethereum_public_key`.
| `concent_use_case`              | `ConcentUseCase`      | no       | Use case in which Concent claim the deposit.
| `amount`                        | decimal               | no       | The amount claimed. Must be greater than zero.
| `tx_hash`                       | string                | yes      | The hash of the Ethereum transaction that will cover the claim. Empty if the transaction has not been created yet.
| `created_at`                    | timestamp             | no       | The creation time of the object.
| `updated_at`                    | timestamp             | no       | Time of the last modification of any field in the object.

#### `DepositAccount` model
- **Database**: `control`

The main purpose of this object is to allow us to put a database lock on all `DepositClaim`s belonging to a specific payer, though it may get another purpose in the future.
Putting locks directly on `DepositClaim` would not work when there are no claims yet.

We never create `DepositAccount` for the payee because the payee may be Concent itself.

| Column name                   | Type                  | Optional | Remarks                                                                                                                 |
|-------------------------------|-----------------------|----------|-------------------------------------------------------------------------------------------------------------------------|
| `client`                      | `Client`              | no       | `Client` who owns the deposit on this account.
| `ethereum_public_key`         | string                | no       | Address of the Ethereum account belonging to the client who owns the deposit account.

#### `ConcentUseCase` enum
- `ForcedAcceptance`
- `AdditionalVerification`
- `ForcedPayment`


### Communication examples

####  Initial state
Deposits:

| owner | deposit account | amount |
|-------|-----------------|--------|
| A     | A1              | 5 GNT  |
| A     | A2              | 0 GNT  |
| B     | B1              | 0 GNT  |
| C     | C1              | 0 GNT  |
| D     | D1              | 7 GNT  |
| E     | E1              | 0 GNT  |


`DepositClaim`s:

| id   | subtask | client | deposit account | use case                 | amount | `tx_hash` |
|------|---------|--------|-----------------|--------------------------|--------|-----------|
| DC1  | S1      | A      | A1              | `ForcedAcceptance`       | 3 GNT  | `None`    |
| DC2  | S2      | A      | A2              | `ForcedAcceptance`       | 7 GNT  | `None`    |
| DC3  | S3      | B      | B1              | `AdditionalVerification` | 5 GNT  | 020202    |
| DC4  | S3      | C      | C1              | `AdditionalVerification` | 1 GNT  | 030303    |


- `Subtask` objects for all subtasks referenced by claims already exist.
    - Same for `DepositAccount`s.
- There are no active database locks.
- SVT = 400
- FAT = 100
- CMT = 50

#### Sequence 1: client D forces client A to accept subtask S10
- **[t=500]** Client D agrees to compute subtask S10 for client A.
    - `TaskToCompute.timestamp`: 500.
    - `TaskToCompute.deadline`: 600.

- **[t=1001]** Client D submits `ForceSubtaskResults` message to `send/` endpoint.
    - Task parameters:
        - subtask_id: S10
        - total price (`TaskToCompute.price` * task duration): 10 GNT
        - requestor's Ethereum account: A1
        - provider's Ethereum account: D1
    - **[t=1002]** Concent validates the message and determines that the request is valid.
    - **[t=1003]** Concent makes a HTTP request to `bankster/claim-deposit/` endpoint.
        - `concent_use_case`: `ForcedAcceptance`
        - `subtask_cost`: 10 GNT

- **[t=1010]** Bankster handles a request to `bankster/claim-deposit/` endpoint.
    - Claim calculation:
        - claim against requestor: 10 GNT
        - claim against provider: 0 GNT
    - **[t=1011]** Initialization
        - `Client` instance for client A already exists.
        - `DepositAccount` instance for ethereum account A1 already exists.
    - **[t=1012]** Deposit query
        - Bankster calls `get_deposit_value(A1)` from SCI.
        - SCI makes a HTTP request to the Ethereum client.
        - The response is 5 GNT.
    - **[t=1020]** Claim freeze
        - Bankster puts a database lock on `DepositAccount` A1.
    - **[t=1021]** Requestor's spare deposit check
        - Sum of deposit claims against A1: 3 GNT.
        - 3 GNT (claims) < 5 GNT (deposit).
    - **[t=1022]** Deposit lock
        - Bankster creates `DepositClaim` DC10
            - payer deposit account: A1
            - payee: D1
            - subtask: S10
            - use case: `ForcedAcceptance`
            - amount: 10 GNT
            - `tx_hash`: `None`
    - **[t=1023]** Unfreeze and response
        - Bankster releases the lock from `DepositAccount` A1.
        - Bankster commits database transaction.
        - Bankster returns a response.
            - `claim_against_requestor`: DC10
            - `claim_against_provider`: `None`

- **[t=1030]** Response from Bankster, processing in `send/` continues.
    - **[t=1031]** Concent creates `Subtask` S10.
    - **[t=1032]** Concent adds `ForceSubtaskResults` to the receive queue of client A.
    - **[t=1033]** Concent commits database transaction.
    - **[t=1033]** Concent returns a HTTP response to client D.

 **[t=1100]** A transaction is published on the blockchain
    - Transfer of 1 GNT from client A's Ethereum account A1 to the corresponding deposit account A1. His deposit is now 6 GNT.

- **[t=1160]** Client D makes a request to the `receive/` endpoint.
    - The requestor has not submitted `ForceSubtaskResultsResponse` and it's already past deadline + SVT + FAT + CMT.
    - **[t=1161]** Concent updates `Subtask` S10 due to the timeout.
    - **[t=1164]** Concent makes a HTTP request to `bankster/finalize-payments/` endpoint
        - `deposit_claim_dispositions`:
            - `{'deposit_claim': 10, 'pay': True}`

- **[t=1170]** Bankster handles a request to `bankster/finalize-payments/` endpoint.
    - Deposit query
        - Bankster calls `get_deposit_value(A1)` from SCI
        - SCI makes a HTTP request to the Ethereum client.
        - The response is 6 GNT
    - **[t=1180]** Claim freeze
        - Bankster puts a database lock on `DepositAccount` A1
    - **[t=1181]** Payment calculation
        - Sum of other deposit claims against deposit account A1: 3 GNT
        - `DepositClaim.amount` in DC10 lowered to 3 GNT
    - **[t=1182]** Transaction
        - Bankster calls `force_subtask_payment(DC10, D1, 3 GNT, S10)` from SCI
        - Transaction successfully created with `tx_hash` `101010`
        - Bankster sets `DepositClaim.tx_hash` to `101010`
    - **[t=1190]** Unfreeze
        - Bankster releases the lock from `DepositAccount` A1
        - Bankster commits database transaction
    - **[t=1195]** Response
        - `success`
            - DC10: `True`

- **[t=1210]** Response from Bankster, processing in `receive/` continues.
    - **[t=1211]** Concent adds `SubtaskResultsSettled` to providers receive queue.
    - **[t=1212]** Concent adds `SubtaskResultsSettled` to requestor's out-of-band receive queue.
    - **[t=1213]** Concent commits database transaction.
    - **[t=1214]** Concent returns a HTTP response to client D.
