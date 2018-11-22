### 0.10.2

#### Endpoints and uses cases in general
- Bugfix: Superfluous keyword arguments in `get_list_of_payments()` cal (PR: #963)

#### Compatibility
- golem-messages: 2.15.0
- golem-smart-contracts-interface: 1.6.0

#### Payments
- Bugfix: Add method to remove '0x' prefix from ethereum_transaction_hash (PR #964).

### 0.10.1

#### Endpoints and uses cases in general
- `send` now returns `ServiceRefused` with reason `TooSmallProviderDeposit` for additional verification use case when Provider's deposit is insufficient(#567).
- Add single retry attempt for storing (creating) subtask (#759).
- Add support for multiple protocol version (#916).
- Bugfix: Extend descriptions of errors from golem-messages (#932).

#### Payments
- Concent now uses Bankster to claim deposits (#567).
- Concent now uses Bankster to pay for additional verification as provider (#568).
- Concent now uses Bankster to pay for subtask as requestor (#568).
- Concent now uses Bankster to process `force payment` use case (#565).
- Concent now uses Bankster to `settle overdue acceptances` operation (#898).
- Concent now uses Bankster to `discard claim` operation (#907).
- Concent now uses Bankster to finalize payment (#922).

##### New settings
- `ADDITIONAL_VERIFICATION_COST` (#567).
- `ADDITIONAL_VERIFICATION_CALL_TIME` (#840).

#### Signing Service and Middleman
- Add "Extension #5". Check daily limit for transactions and send email notifications(#872).
- Improve logging (#874).

#### Admin panel
- Lists deposit claims and accounts with all the relevant columns (#944).

### 0.10.0
#### Compatibility
- golem-messages: 2.15.0
- golem-smart-contracts-interface: 1.6.0

#### Endpoints and uses cases in general
- Storage cluster now notifies Concent Core about finished upload (#667).
- Bugfix:  Concent doesn't accept a float in the `TaskToCompute.CompTaskDef['deadline']` definition
- Bugfix:  Processing timeouts in separate transaction (#879).

#### Signing Service and Middleman
- Bugfix: Signing Service is now aware of broken connection to MiddleMan (#861).
- Bugfix: Heartbeat workaround for nginx dropping connection (#892).

##### New settings
- `GNT_DEPOSIT_CONTRACT_ADDRESS`

### 0.9.0
#### Signing Service and Middleman
- Signing Service and Middleman are now fully implemented but disabled by default (#673, #633, #616, #629, #618, #625, #632).
- Concent can now be configured to use Signing Service instead of signing transaction by itself (#635).
- Authentication between Middleman and Signing Service (#631, #630).
- More consistent command-line options for passing secrets to the Signing Service (#671).
- Signing Service can now be configured to send crash reports to Sentry (#762).
- Bugfix: The installation script (`setup.py`) no longer requires golem-messages to be already installed (#800).
- Bugfix: Middleman was not properly cancelling asyncio tasks (#799).
- Bugfix: Fixed error in task scheduling in `QueuePool` in Middleman (#790).
- Bugfix: Fixed incorrect handling of escaped byte followed by related escape sequence in Middleman protocol (#844).

#### Admin panel
- Admin panel can show tasks that might still have active downloads (#329).
- Creation and modification timestamps are now displayed for more models in the admin panel (#709).
- Timed out tasks whose state has not been updated yet are no longer displayed as active in the admin panel (#668).
- The shutdown bar in the admin panel now shows the time limit for active downloads (#444).

#### Endpoints and uses cases in general
- `receive-out-of-band/` and `receive/` now return the same messages and receive-out-of-band/ is deprecated (#787).
- Concent now expects `task_id` and `subtask_id` to always be valid UUIDs (#705).
- Additional consistency checks for nested messages in messages stored in the database (#177).
- Bugfix: Starting another use case in the same subtask caused a crash (#195).
- Bugfix: Concent now properly locks subtasks before modifying them to prevent race conditions (#753).
- Bugfix: Concent could start a use case twice in some cases due to a race condition in the endpoints (#770).

#### Payments
- Bugfix: Concent would try to remove confirmed transaction from transaction pool multiple times and fail (#693).

#### Additional verfication use case (UC4)
- Bugfix: FileUploadToken had completely wrong deadline in verification use case (#827).
- Bugfix: Celery workers were not checking if a subtask is timed out before processing it (#779).
- Bugfix: File names and paths in verification tasks were not being parsed and validated correctly (#715, #716).
- Bugfix: Verifier used a very inefficient method to download files from the storage server, which caused timeouts (#714, #675).
- Bugfix: Verifier sometimes interpreted exceptions caused by malformed zip file as a crash that needs to be reported (#708).

#### Documentation
- Concent timing diagram (#431).

#### Other
- Bugfix: Added a migration that fixes cached timestamps on messages stored in the database by the previous versions (#690).
- Bugfix: Cluster tests were ignoring Content-Type when decoding server responses (#772).

#### Compatibility
- golem-messages: 2.13.0
- golem-smart-contracts-interface: 1.5.0

#### Manual migrations
Manual configuration, database and scripting changes that may be necessary to successfully migrate from the previous version:

##### New settings
- `MIDDLEMAN_ADDRESS`
- `MIDDLEMAN_PORT`
- `SIGNING_SERVICE_PUBLIC_KEY`

##### Modified settings
- `CONCENT_ETHEREUM_ADDRESS` has been replaced with `CONCENT_ETHEREUM_PUBLIC_KEY`.

##### Removed settings
- `MOCK_VERIFICATION_ENABLED`

##### New features
- The use of the Signing Service is disabled by default.
  Change the value of the `USE_SIGNING_SERVICE` setting if you want to enable it.

#### Installation
- A file called `RELEASE-VERSION` must now exist in the `middleman_protocol/` and `signing_service/` subdirectories at installation time.

### 0.8.0
#### Forced payment use case (UC5)
- Bugfix: ForcePaymentRejected.force_payment was not being filled in the forced payment use case (#548).
- Bugfix: Concent would accept ForcePayment containing SubtaskResultsAccepted from multiple requestors or providers or with multiple Ethereum accounts of the same requestor or provider (#545, #664, #665).
- Implemented a mechanism to properly synchronize nonce between different SCI instances: DatabaseTransactionsStorage (#584).

#### Additional verfication use case (UC4)
- Added support for subtasks that render multiple images in additional verification use case (#537).
- In the additional verification use case Concent now renders only the fragment of the image defined in the subtask definition (#520).
- Lower time limits in result transfer and verification use cases are no longer enforced (#532, #538).
- Timeout for verification is no longer constant and based on AVCT (#556).
- Timeout for rendering with Blender is now always consistent with the timeout for the whole verification use case (#557).
- Bugfix: task_owner_key included in ForcePaymentCommitted was not hex-encoded (#580).
- Bugfix: Verification was failing instead of reporting a mismatch when compared result images had different dimensions (#535).
- Bugfix: Verifier was not unpacking the Blender scene file correctly (#528).
- Bugfix: Verifier was accessing the storage server using the external address which is only accessible over HTTPS (#577).
- Bugfix: Conductor would not report finished upload if the client uploaded a file more than once (#540).
- Bugfix: Concent would crash when processing a report about finished upload of all verification files because it tried to access a deprecated setting to compute SVT (#576).
- Bugfix: Corrupted or invalid achives uploaded in additional verification use case resulted in verifictation failures rather than a mismatch (#610).
- Bugfix: Very long subtask_id or task_id could result in an error due to the maximum path length being exceeded (#598).

#### Concent Signing Service
- Partial implementation of Signing Service and Middleman. Not usable yet (#599, #623, #615).

#### Validations and error handling
- Stronger validations for ForceSubtaskResultsResponse (#666, #662).
- Bugfix: Signatures of nested messages were not always verified (#458, #547)
- Bugfix: Some error messages included numeric message type codes rather than their class names (#457).
- Bugfix: TaskToCompute.ComputeTaskDef was not being validated which resulted in crashes in cases where the client should get a HTTP 4xx response (#600).

#### Database
- Modification and creation timestamps are now stored for more objects in the database (#604).
- Bugfix: Added missing migration for a change introduced in in 0.7.3 - ForceGetTaskResult should have been added to older messages in the database (#573).
- Bugfix: Concent was storing received messages with current time instead of the actual timestamp (#627). This may have affected deadline calculations.

#### Deployment and administration
- Time in dates displayed in the admin panel is now in 24-hour format (#552).
- Now we display creation and modification time in the admin panel whenever available (#553).
- More validity checks for settings (#589).
- Dependencies updated to the latest versions (#554).

#### Development
- Default settings in development that contain local URLs adjusted to work better with the virtual machine for testing.
- pytest is now used by default for running unit tests (#539).
- Bugfix: SVT and MDT were not being calculated based on settings even if custom protocol times were enabled.

#### Compatibility
- golem-messages: 2.10.1
- golem-smart-contracts-interface: 1.5.0

### 0.7.3
- Bugfix: A hard-dependency on OpenCV prevented Concent from running in containers where it's not installed (only Verifier has it installed in our deployment)

### 0.7.2
- More complete verifier implementation (still only partially implemented though):
    - Actually running Blender
    - Uploading rendering result to the storage server
    - Comparing rendering results and deciding whether they match
- All verification components except for verifier are now functional. Verifier can be disabled in settings to prevent the incomplete implementation from causing problems in production. In that case a mock is used which makes an arbitrary decision based solely on subtask_id.
- Admin panel now displays a bar indicating the time left until soft shutdown at the top of the page.
- ForceGetTaskResult in included in ForceGetTaskResultUpload/Download messages is now the one signed and submitted by the requestor, not one created by Concent.
- Concent now validates the data that ends up in FileTransferToken.
- Messages received by Concent Core are now logged (in decoded form).
- More verbose logging in Concent Core.
- Crashes in Celery task handlers are now reported to Sentry.
- Bugfix: Concent was generating invalid tokens for its own use when checking if files have been uploaded in the result transfer use case (UC2). It resulted in the client being unable to finish the use case successfully.
- Bugfix: Concent was sending bare SubtaskResultsRejected to the provider instead of wrapping it in ForceSubtaskResultsResponse.
- Bugfix: Reason in ForceReportComputedTaskResponse generated by Concent was not being set correctly.
- Bugfix: The rare code path that gets triggered if the client manages to upload files for verification before the message from the control cluster gets to the storage cluster was not notifying the control cluster about finished upload which resulted in the timeout of the upload phase.
- Bugfix: Time limits for file upload in verification use case were not being enforced.
- Bugfix: ADDITIONAL_VERIFICATION_CALL_TIME was missing in the response from the protocol-constants endpoint.
- Bugfix: The information about verification outcome was being processed by the wrong component which resulted in a failure to deliver the response to the client.
- Bugfix: Conductor (running on the storage cluster) was trying to get part of the task information from the database that's present only on the control cluster.
- Bugfix: Verifier was overwriting source package with the result package and failing if task and subtask IDs were the same.
- Bugfix: There was no time limit for additional verification.
- Bugfix: ForceGetTaskResult and SubtaskResultsVerify were being accepted even if sent too early.
- Bugfix: Conductor's endpoints were not enforcing POST method.
- Bugfix: Celery task handles did not wrap all their database operations in a transaction.
- Bugfix: HTTP 5xx errors were not reported in the default JSON format when JSON had the same weight as HTML but not specified explicitly in the Accept header.
- Supports golem-messages 2.9.5 and golem-smart-contract-interface 1.1.1

### 0.7.1
- Bugfix: TaskToCompute.deadline validations were converting the value to an integer which resulted in spurious validation errors.
- Bugfix: Hashes and all the other data that eventually gets into a FileTransferToken was not validated until the token was actually used. Now it's also validated when the token is constructed.
- Bugfix: Concent was expecting SubtaskResultsVerify to be signed by the requestor, not the provider.
- Bugfix: File paths in FileTransferToken in verification use case were generated in a wrong way (sometimes task ID was swapped with subtask ID).
- Bugfix: Timeout for accepting ForceGetTaskResult was still using invalid formula based on FORCE_ACCEPTANCE_TIME.
- Bugfix: The original message from signature validation exception is no longer suppressed if present. It's now included in the HTTP 400 response.

### 0.7.0
- The internal message flow in the additional verification use case is now complete (i.e. starting the verification and getting the response, not the verification itself).
    - The control cluster now actually sends a verification request to the storage cluster when the client contacts it.
    - The control cluster now processes the verification result and generates responses.
    - The control cluster enforces verification timeouts.
    - If a verification succeeds, the provider gets paid from requestor's deposit.
    - Notifying the control cluster when all files are ready and starting the process when it acknowledges them.
- Partial implementation of verifier (the component responsible for rendering and image comparison during verification):
    - Downloading and unpacking source and result packages uploaded by the provider.
- Each component (concent, conductor, verifier) now has its own Celery queue to prevent messages meant for it getting stuck behind bigger tasks meant for other components.
- Concent now reports an error TaskToCompute messages nested in ForcePayment do not have the same IDs.
- Each file listed in FileTransfer token now declares its purpose.
- HTTP 5xx responses are now using JSON content type by default. The client can choose between HTML and JSON responses by including the Accept header.
- Cleanup and minor bugfixes in the command-line testing tool.
- Refactored the code that overrides protocol times. A new setting now controls this behavior (CUSTOM_PROTOCOL_TIMES).
- As a temporary security measure subtask and task IDs can contain only alphanumeric characters, dashes and underscores.
- Migrations have been squashed. Database has to be cleared before upgrading from previous versions.
- Supports golem-messages 2.9.5 and golem-smart-contract-interface 1.1.1

### 0.6.0
- Full authentication based on TaskToCompute and ClientAuthorization messages. Passing public keys in HTTP headers is no longer needed.
- Real payment backend and its configuration. Concent can now interact with the smart contract on the blockchain.
- Soft shutdown of the control cluster can now be initiated in the admin panel. There are also filters showing subtasks that are still active.
- Partial implementation of the additional verification use case: starting the use case on the control cluster and monitoring uploads to the storage cluster and initiating verification tasks. The feature is not usable yet.
- Time limits for upload and verification (MAXIMUM_DOWNLOAD_TIME and SUBTASK_VERIFICATION_TIME) are no longer constants. Now they depend on file sizes and time allotted for the computation.
- Constants from golem-messages are now used as defaults for timing settings.
- If requestor sends a diffrerent ReportComputedTask than the one submitted by the provider, now the one from the requestor is taken into account.
- AckReportComputedTask generated by Concent is now signed separately from the outer message so that it can be taken out and used separately.
- RejectReportComputedTask is no longer generated by Concent when it refuses service due to a timeout.
- Initial version of command-line testing tool.
- All JSON error messages now contain error codes in addition to human-readable messages.
- E-mail error reports are now disabled. Errors are reported only to Sentry.
- Integration tests now use protocol-constants/ endpoint to make sure times match server configuration. They've also gone through a lot of refactoring to make them give better feedback.
- More startup checks to detect invalid settings.
- Stricter database constraints for the subtask table.
- Removed support for RejectReportComputedTask.REASON.TaskTimeLimitExceeded.
- Bugfix: Concent was expecting the wrong party to sign nested messages in the computation report use case.
- Bugfix: Tokens used for checking if files have been uploaded to the storage cluster had wrong signature and checksum format. Keys were also not consistently stored/validated as bytes rather than str.
- Bugfix: Gatekeeper was rejecting uploads with Content-Type other than application/x-www-form-urlencoded.
- Bugfix: HTTP 401 from gatekeeper received by the control cluster in response to a file status check was interpreted as a missing file rather than an error.
- Bugfix: TooSmallProviderDeposit was reported instead of TooSmallRequestorDeposit in the acceptance use case.
- Bugfix: Validations of rejection reason and nested messages inside RejectReportComputedTask were not correct.
- Supports golem-messages 2.9.0 and golem-smart-contract-interface 1.1.0

### 0.5.2
- Added Celery to the project in anticipation of the upcoming 'additional verification' use case.
- Time windows in 'report computed task', 'force subtask results', 'force get task result' and 'force payment' use cases updated to match the current spec.
- Bugfix: Fixed connecting to the storage cluster with a self-signed certificate.
- Bugfix: FileTransferToken sent to the provider inside ForceGetTaskResultUpload was not signed separately from the containing message and was unusable to the client.
- Bugfix: FileTransferToken sent to the provider had empty subtask_id.
- Supports golem-messages 2.0.0.

### 0.5.1
- Support for self-signed certificates on the storage cluster (still buggy).
- Naming convention for files uploaded to the storage cluster now matches the one used by Golem. The file with rendering results from provider is now called `blender/result/{task_id}/{task_id}.{subtask_id}.zip`.
- Test runner now supports running tests in parallel on multiple cores.
- Bugfix: FileTransferTokens for Concent's internal use used wrong operation ('upload' instead of 'download').
- Bugfix: Database changes are now rolled back in case of a HTTP 4xx response.
- Bugfix: Fixed errors caused by logging code sometimes trying to get values that were not available.
- Bugfix: TaskToCompute with an empty key no longer passes validations.
- Bugfix: Minor fixes in integration tests.
- Supports golem-messages 2.0.0.

### 0.5.0
- Internal logic of the API server rewritten to behave like a state machine.
    - The transitions between states were not well defined before. Now every subtask can be in only one state at a time and only specific transitions are allowed.
    - Getting messages from `receive/` and `receive-out-of-band/` endpoints can no longer affect the outcome of a use case. The client never should have been required to actually fetch messages queued for it.
    - Server's behavior may have changed in various corner cases. It should now all be compliant with the specification.
- New endpoint that returns values of all settings that determine protocol timings used by Concent (/api/v1/protocol-constants/).
- Concent version is now included in every response from the API server (Concent-Version HTTP header).
- The app can now be configured to submit crash reports can to an instance of sentry.io.
- Bugfix: Subtasks are now identified by subtask_id instead of task_id. Concent always works on individual subtasks, not the whole task.
- Bugfix: API server was using wrong download path when checking if files have already been uploaded to the storage cluster.
- Bugfix: Checksum validation in gatekeeper was too lenient and allowed newlines.
- More tests for the 'force payment' use case.
- TOKEN_EXPIRATION_DEADLINE setting renamed to TOKEN_EXPIRATION_TIME.
- The minimum supported Python version is now 3.6.
- Supports golem-messages 1.16.1

### 0.4.0
- Initial implementation of the forced payment use case. For now without actual blockchain access (all interation with the blockchain is mocked).
- Concent API server updated to support the new wrapping messages added in golem-messages 1.9.0. Now the server always creates the outer message by itself and never resends a message received from one client directly to another client.
- Concent was using naive timestamps in localtime internally. Switched to timezone-aware UTC-based timestamp and implemented datetime helpers to keep it that way.
- Bugfix: The time windows in the 'force subtask results' use case were starting too early. Should have been based on the SVT (subtask verification time) interval but was using CMT (concent messaging time) instead.
- Bugfix: Requestor's time window in the 'force subtask results' was incorrectly starting as soon as provider submitted the force message. Should have been starting after a predefined time interval (FAT).
- Bugfix: receive/ was not checking if the ForceSubtaskResultsResponse submitted by the requestor really contains the acceptance or rejection.
- Bugfix: Fixes in the authentication code.
- More information is now being logged by Concent API server to allow better monitoring.
- Supports golem-messages 1.10.0.
- Now works with OpenSSL 1.1 and does not require patching for 1.0 (due to golem-messages switching to Golem's own fork of pyelliptic).

### 0.3
- Full implementation of the 'force subtask results' use case.
- Supports golem-messages 1.8.0.

### 0.2.3
- Supports golem-messages 1.7.0.
- Support for file checksum and size verification in gatekepper (information is now passed to nginx-storage in response headers.
- Clients are now identified based on the submitted public key. Messages are no longer delivered indiscriminately to any client that contacts the service.
- More reliable detection of invalid messages thanks to better error reporting in golem-messages 1.7.0.
- Bugfix: task_id in messages is now expected to be a string and properly validated as such.
- Bugfix: gatekeeper properly adds the WWW-Authenticate header to HTTP 401 responses.
- Bugfix: the API server no longer requires gatekeeper feature to be enabled to generate tokens.

### 0.2.1
- Bugfix: Validations of the deadline field in TaskToCompute have been relaxed.
  Now any value that can be converted to int is accepted.

### 0.2
- Full implementation of the 'force get task result' use case.
- Supports golem-messages 1.6.0.
- `send/` endpoint no longer accepts JSON messages.
- Timestamps on messages submitted to `send/` are now checked and enforced. Messages with timestamps far in the past or in the future result in HTTP 400.
- Sending a message with empty `Content-Type` HTTP header now results in a JSON response (not HTML).

### 0.1.1
- Fixed several corner cases in the 'force report computed task' use case.
- Fixed issues related to validating signature and storing signed messages in the database.
- Gatekeeper now allows HEAD requests.
- More verbose logging in gatekeeper.
- Internal changes in how Golem message types are stored in the database.
- Extensive refactoring and cleanup for the endpoint code.

### v0.1
- Full implementation of the 'force report computed task' use case
- Partial implementation of the 'get task result' use case (gatekeeper)
