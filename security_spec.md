# Security Specification for UAE Gaming Deals

## 1. Data Invariants
- A `Deal` must reference a valid `Product` (or we store product data within the deal for redundancy/performance).
- `AlertSubscription` must have at least an email or whatsapp number.
- `price` in `Deal` must be positive.
- `discountPercentage` must be between 0 and 100.

## 2. The "Dirty Dozen" Payloads
1. **The Ghost Field Attack**: Attempt to add `isAdmin: true` to a Deal update.
2. **Identity Spoofing**: User A trying to update User B's alert subscription.
3. **Price Manipulation**: Trying to set a deal price to -100.
4. **ID Poisoning**: Using a 1MB string as a `dealId`.
5. **Orphaned Writes**: Creating a Deal without a `productId`.
6. **Self-Promotion**: An unauthenticated user trying to create a Deal (only system/admin should).
7. **PII Exposure**: Trying to read all alert subscriptions (should be restricted).
8. **Resource Exhaustion**: Inserting a 2MB JSON object into `specs`.
9. **Timestamp Spoofing**: Setting `updatedAt` to a future date instead of `request.time`.
10. **Category Injection**: Adding "illegal" categories to an alert subscription.
11. **Store Faking**: Updating a deal to change the store name to something malicious.
12. **Blanket Read Scam**: Trying to `list` all subscriptions without authentication.

## 3. Test Runner (Draft)
A `firestore.rules.test.ts` will be implemented to verify these.

## 4. Permissions Matrix
- `products`:
  - `read`: Anyone (including anonymous)
  - `write`: Admins only
- `deals`:
  - `read`: Anyone
  - `write`: Admins only
- `subscriptions`:
  - `create`: Anyone (public can sign up for alerts)
  - `read/update/delete`: Owner only (if we had accounts) or blocked for now (since "No logins required"). Since no login is required, we'll allow creation but reading should be restricted or handled via a unique token if needed. For now, we'll allow creation and strict read-by-self if we implement a token, or just block read for simplicity as per "No logins required".
