# HTTP Status Codes — A Practical Reference

The Hypertext Transfer Protocol (HTTP) uses three-digit **status codes** in the
response to indicate the result of the server's attempt to satisfy a request.
The first digit defines the class of response. The descriptions below are
factual summaries of the standard semantics (RFC 9110 and predecessors).

## 1xx — Informational

The request was received and the process is continuing.

- **100 Continue**: the initial part of a request has been received and the
  client should continue with the rest of the request.
- **101 Switching Protocols**: the server is switching to a different protocol
  as requested by the client, for example to upgrade to WebSocket.

## 2xx — Success

The request was successfully received, understood, and accepted.

- **200 OK**: the request succeeded. The meaning of success depends on the HTTP
  method used.
- **201 Created**: the request succeeded and a new resource was created, for
  example after a POST that adds a record.
- **204 No Content**: the server successfully processed the request and is not
  returning any body. Commonly returned by a successful DELETE.

## 3xx — Redirection

Further action is needed to complete the request.

- **301 Moved Permanently**: the target resource has been assigned a new
  permanent URI. Clients and caches should update their references.
- **302 Found**: the target resource resides temporarily under a different URI.
- **304 Not Modified**: there is no need to retransmit the resource; the
  client's cached copy is still valid.

## 4xx — Client errors

The request contains bad syntax or cannot be fulfilled.

- **400 Bad Request**: the server cannot process the request due to a client
  error such as malformed syntax.
- **401 Unauthorized**: authentication is required and has failed or has not
  been provided.
- **403 Forbidden**: the server understood the request but refuses to authorize
  it. Unlike 401, re-authenticating will not help.
- **404 Not Found**: the server cannot find the requested resource. This is one
  of the most recognizable codes on the web.
- **429 Too Many Requests**: the user has sent too many requests in a given
  amount of time ("rate limiting").

## 5xx — Server errors

The server failed to fulfill an apparently valid request.

- **500 Internal Server Error**: a generic error message given when an
  unexpected condition was encountered and no more specific message is suitable.
- **502 Bad Gateway**: the server, while acting as a gateway or proxy, received
  an invalid response from an upstream server.
- **503 Service Unavailable**: the server is not ready to handle the request,
  often because it is overloaded or down for maintenance. A health check that
  reports a degraded dependency commonly returns 503.
- **504 Gateway Timeout**: the server, acting as a gateway, did not receive a
  timely response from an upstream server.

## Choosing the right code

Returning an accurate status code matters because clients, caches, and
monitoring systems all act on it. For example, a search crawler treats **301**
very differently from **302**, and an uptime monitor distinguishes a healthy
**200** from a degraded **503**. Using **404** for a missing record but
**400** for a malformed identifier gives API consumers precise, actionable
feedback.
