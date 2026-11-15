--
-- Lets a service that holds only the publishable key (the portrait renderer)
-- check a device token. True only for an active (paired) device; false for an
-- unknown, unpaired or deactivated one. Reveals nothing else about the device.
create function printer.check_device(device_token text) returns boolean
language sql stable security definer set search_path = ''
as $$ select printer._active_device(device_token) is not null $$;


-- Lock every function, then open the API ones (see the printer migration).
revoke all on all functions in schema printer from public, anon, authenticated, service_role;
grant execute on function printer.register_device(text)               to anon, authenticated, service_role;
grant execute on function printer.send_print(text, text, jsonb, text) to anon, authenticated, service_role;
grant execute on function printer.claim_jobs(text, int)               to anon, authenticated, service_role;
grant execute on function printer.finish_job(text, bigint, text)      to anon, authenticated, service_role;
grant execute on function printer.list_fonts(text)                    to anon, authenticated, service_role;
grant execute on function printer.get_font(text, text)                to anon, authenticated, service_role;
grant execute on function printer.upload_font(text, text, text)       to anon, authenticated, service_role;
grant execute on function printer.delete_font(text, text)             to anon, authenticated, service_role;
grant execute on function printer.check_device(text)                  to anon, authenticated, service_role;
