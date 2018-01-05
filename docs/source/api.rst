Concent API
###########

Concent API provides means for message exchange between Concent and Golem clients.

It's not a typical REST API.
Messages are in the same exact format as messages exchanged between Golem clients using the P2P protocol.
HTTP is used only as a transport mechanism.

Endpoints
+++++++++

The API offers three endpoints:

- `POST /api/send/` - used to send messages to Concent.

  The body of the request must contain exactly one message from the client.

  The response body may contain a single message that Concent wants to pass back to the client.
  It may also be empty.

- `POST /api/receive/` - used by the client to collect messages sent by Concent.

  HTTP protcol does not provide any means for the server to initiate a connection with the client.
  For that reason it is assumed that the client asks the Concent server for pending messages at times designated by the protocol.

  The response body may contain the single message for the client or be empty if there are no pending messages.

- `POST /api/receive-out-of-band/` - used by the client to collect out-of-band messages sent by Concent.

  Works just like `/receive/` with the difference that it only returns messages that are not a part of the real-time exchange in the protocol.
  These messages serve mainly as notifications to the other party that an event occurred.
  They are meant to be delivered using a mechanism separate from the normal messages and preserved for a significant period of tiem if the client can't receive them immediately.

Endpoints accept no query parameters.
All information is passed in HTTP headers and message body.

Request and response body
+++++++++++++++++++++++++

The content in the body of HTTP requests and responses can be in one of two formats:

- Golem's binary protocol (`Content-Type: application/octet-stream`)
- JSON (`Content-Type: application/json`)

Request and response headers
++++++++++++++++++++++++++++

`Content-Type`
==============

Both request and response must specify `Content-Type` if the body is not empty.
Otherwise this header should be omitted.

`Accept`
========

The `Accept` header on the request can be used to indicate a preference between the supported response content types.

To accept any format, use `*/*`.

If the server does not support any of the formats listed, it responds with `HTTP 406 NOT ACCEPTABLE`.

Examples:

- `Accept: */*`
- `Accept: application/octet-stream`
- `Accept: application/octet-stream; application/json;q=0.5, */*;q=0.3`

`Content-Length`
================

Standard HTTP header that indicates the length of the body or a request or response.

`Concent-Pending-Message-Count`
===============================

A custom HTTP header returned from `/api/send/`, `/api/receive/` and `/api/receive-out-of-band/` to indicate the number of protocol messages waiting for the client on the server, not including the one included in the response.

The client can use the `/api/receive/` to fetch the next pending message.

`Concent-Pending-Out-Of-Band-Message-Count`
===========================================

A custom HTTP header returned from `/api/send/`, `/api/receive/` and `/api/receive-out-of-band/` to indicate the number of out-of-band messages waiting for the client on the server, not including the one included in the response.

The client can use the `/api/receive-out-of-band/` to fetch the next pending message.

HTTP statuses and errors
++++++++++++++++++++++++

- All endpoints

  - `HTTP 400 BAD REQUEST` - The message is not well formed and cannot be processed.
    The response body contains information about the error either as JSON or Golem protocol message.
    There's no return message.

  - `HTTP 406 NOT ACCEPTABLE` - The server does not support any of the formats listed in the `Accept` header on the request.

  - `HTTP 415 UNSUPPORTED MEDIA TYPE` - The server does not know how to process the data in the request.

    Usually a result of sending an unsupported `Content-Type`.

  - Other `HTTP 4xx` errors - The message could not be processed due to a problem that under client's control.
    The request is invalid or used inappropriately.

  - `HTTP 5xx` errors - The sever encountered an internal problem and could not finish processing the request.
    All changes to the server state were immediately rolled back.

    The response body contains information about the error in JSON format.

    All the changes in the state Any changes  attempt was 

- `POST /api/send/`

  - `HTTP 200 OK` - The message was accepted and processed immediately.
    The return message is included in the response.

  - `HTTP 202 ACCEPTED` - The message was accepted and and will be processed later.
    The response is empty and the return message (if any) will be sent asynchronously.

    The client can collect the return message from the `/api/receive/` endpoint once the processing has finished.

  - `HTTP 204 NO CONTENT` - The message was accepted and processed immediately.
    There's no return message.

- `POST /api/receive/` - used by the client to collect messages sent by Concent.

  - `HTTP 200 OK` - There was at least one pending message and it was included in the response.

  - `HTTP 204 NO CONTENT` - There were no pending messages.
    Response body is empty.

- `POST /api/receive-out-of-band/` - used by the client to collect out-of-band messages sent by Concent.

  - `HTTP 200 OK` - There was at least one pending message and it was included in the response.

  - `HTTP 204 NO CONTENT` - There were no pending messages.
    Response body is empty.
