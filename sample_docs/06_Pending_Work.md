# Pending work - handover note from Arjun

## Pending
- Payment gateway integration: webhook signature verification is still pending and must be done before go-live.
- Finish the inventory sync job: batch the warehouse API calls to fix the timeout (see BUG-118).
- Set up production deployment on AWS Mumbai.
- Write the load test for 500 concurrent users using Locust.

## Next steps
- Fix BUG-112 using the idempotency_key column that is already in the database.
- Get DLT template approval for SMS before starting SMS notifications.

## Who to ask
- Ask Priya Nair about scope changes and client deadlines.
- Contact Rahul Desai for warehouse API credentials and VPN.
