-- Device-style navigation is not financial consent. Subscribe still owns the
-- explicit human decision and the service-authenticated entitlement receipt.
ALTER TABLE billing_sessions ADD COLUMN user_code TEXT;
CREATE UNIQUE INDEX billing_sessions_user_code ON billing_sessions(user_code)
    WHERE user_code IS NOT NULL;
