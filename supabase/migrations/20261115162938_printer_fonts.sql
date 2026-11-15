-- Extra fonts, shared by every paired printer. Built-in fonts ship in the
-- repo; these are uploaded from a printer's page and synced to all paired
-- printers. Only active devices can list, read, upload or delete them, so
-- fonts you may not redistribute never become public.

create table printer.fonts (
  name        text primary key
              check (name ~ '^[A-Za-z0-9_.-]{1,80}\.(ttf|otf|ttc|TTF|OTF|TTC)$'),
  data        bytea not null check (octet_length(data) <= 10485760),
  sha256      text not null,
  uploaded_by uuid references printer.devices (id) on delete set null,
  created_at  timestamptz not null default now()
);
alter table printer.fonts enable row level security;
revoke all on printer.fonts from anon, authenticated;


-- Private helper: the id of the active device holding this token, or null.
create function printer._active_device(device_token text) returns uuid
language sql stable security definer set search_path = ''
as $$ select d.id from printer.devices d
      where d.token_hash = printer._hash(device_token) and d.active $$;


create function printer.list_fonts(device_token text)
returns jsonb
language plpgsql security definer set search_path = ''
as $$
begin
  if printer._active_device(device_token) is null then
    raise exception 'device_inactive';
  end if;
  return coalesce((select jsonb_agg(jsonb_build_object(
                     'name', f.name, 'sha256', f.sha256, 'size', octet_length(f.data))
                     order by f.name)
                   from printer.fonts f), '[]'::jsonb);
end $$;


-- Returns the font file as base64.
create function printer.get_font(device_token text, name text)
returns text
language plpgsql security definer set search_path = ''
as $$
#variable_conflict use_variable
declare
  v_data bytea;
begin
  if printer._active_device(device_token) is null then
    raise exception 'device_inactive';
  end if;
  select f.data into v_data from printer.fonts f where f.name = name;
  if v_data is null then
    raise exception 'unknown_font';
  end if;
  return encode(v_data, 'base64');
end $$;


-- `data` is the font file as base64. The device checks it is a real font
-- before sending; every device checks again before using it.
create function printer.upload_font(device_token text, name text, data text)
returns jsonb
language plpgsql security definer set search_path = ''
as $$
#variable_conflict use_variable
declare
  v_dev   uuid := printer._active_device(device_token);
  v_bytes bytea;
  v_sha   text;
begin
  if v_dev is null then
    raise exception 'device_inactive';
  end if;
  if name is null or name !~ '^[A-Za-z0-9_.-]{1,80}\.(ttf|otf|ttc|TTF|OTF|TTC)$' then
    raise exception 'invalid_name' using hint = 'letters, digits . _ - and a .ttf/.otf/.ttc ending';
  end if;
  begin
    v_bytes := decode(data, 'base64');
  exception when others then
    raise exception 'invalid_data' using hint = 'data must be base64';
  end;
  if octet_length(v_bytes) > 10485760 then
    raise exception 'font_too_large' using hint = 'max 10 MB';
  end if;
  v_sha := encode(extensions.digest(v_bytes, 'sha256'), 'hex');
  insert into printer.fonts as f (name, data, sha256, uploaded_by)
  values (name, v_bytes, v_sha, v_dev)
  on conflict on constraint fonts_pkey do update
    set data = excluded.data, sha256 = excluded.sha256,
        uploaded_by = excluded.uploaded_by, created_at = now();
  return jsonb_build_object('name', name, 'sha256', v_sha);
end $$;


create function printer.delete_font(device_token text, name text)
returns boolean
language plpgsql security definer set search_path = ''
as $$
#variable_conflict use_variable
begin
  if printer._active_device(device_token) is null then
    raise exception 'device_inactive';
  end if;
  delete from printer.fonts f where f.name = name;
  return found;
end $$;


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
