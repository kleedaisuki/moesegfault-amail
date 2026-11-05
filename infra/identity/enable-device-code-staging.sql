-- Import into Identity's staging environment migration stream after 0012.
-- Keep the existing client identity and pairwise subject mapping unchanged.
UPDATE oauth_clients
SET device_authorization_enabled = 1, updated_at = unixepoch()
WHERE client_id = 'amail-cli-staging';
