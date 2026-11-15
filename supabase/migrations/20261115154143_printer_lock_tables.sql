-- Exposing the schema in the dashboard granted table rights to anon and
-- authenticated. Nobody but the four API functions touches these tables.
revoke all on all tables    in schema printer from anon, authenticated;
revoke all on all sequences in schema printer from anon, authenticated;
