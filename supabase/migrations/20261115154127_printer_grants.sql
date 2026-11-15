-- The dashboard's Data API page shows a function as "exposed" when anon,
-- authenticated AND service_role can run it. Make the four API functions
-- fully exposed and keep the helper private (it got ticked by accident).
revoke all on function printer._hash(text) from public, anon, authenticated, service_role;
grant execute on function printer.register_device(text)               to service_role;
grant execute on function printer.send_print(text, text, jsonb, text) to service_role;
grant execute on function printer.claim_jobs(text, int)               to service_role;
grant execute on function printer.finish_job(text, bigint, text)      to service_role;
