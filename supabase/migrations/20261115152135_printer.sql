-- printer: the cloud side of the thermal printer.
--
-- Senders (web pages, n8n, curl) and devices use the publishable key and
-- may ONLY call the four API functions at the bottom. anon and
-- authenticated get no table privileges at all; RLS is on with no policies
-- as a second lock. The functions are SECURITY DEFINER and do the checks.
--
-- Call them via PostgREST:  POST /rest/v1/rpc/<function>
--   headers: apikey: <publishable key>, Content-Profile: printer
--   (sb_ keys are not JWTs: no Authorization: Bearer header)

create extension if not exists pgcrypto with schema extensions;

create schema if not exists printer;
grant usage on schema printer to anon, authenticated;

create table printer.devices (
  id            uuid primary key default gen_random_uuid(),
  name          text not null unique,               -- hostname, e.g. printer-a1b2
  token_hash    text not null unique,               -- sha256 hex of the device token
  pairing_code  text not null unique,               -- printed on the pairing slip
  active        boolean not null default false,     -- set by hand to pair
  subscriptions text[] not null default '{}',       -- sources it prints unaddressed, e.g. {showmemo}
  hourly_limit  int not null default 30,            -- jobs/hour for this device, all sources
  created_at    timestamptz not null default now(),
  last_seen     timestamptz
);

create table printer.jobs (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  source      text not null,
  template    text not null check (template in ('markdown', 'image', 'slices', 'showmemo')),
  payload     jsonb not null default '{}',
  device_id   uuid not null references printer.devices (id) on delete cascade,
  status      text not null default 'queued'
              check (status in ('queued', 'printing', 'done', 'failed')),
  attempts    int not null default 0,
  claimed_at  timestamptz,
  printed_at  timestamptz,
  error       text
);

create index jobs_queue_idx       on printer.jobs (device_id, status, id);
create index jobs_device_hour_idx on printer.jobs (device_id, created_at);
create index jobs_source_hour_idx on printer.jobs (source, created_at);
create index jobs_showmemo_idx    on printer.jobs (device_id, (payload ->> 'object_id'))
  where template = 'showmemo';

alter table printer.devices enable row level security;
alter table printer.jobs    enable row level security;
revoke all on all tables    in schema printer from anon, authenticated;
revoke all on all sequences in schema printer from anon, authenticated;


-- Private helper. Never granted.
create function printer._hash(token text) returns text
language sql immutable set search_path = ''
as $$ select encode(extensions.digest(token, 'sha256'), 'hex') $$;


-- A new device signs up. Returns its token exactly once; the database only
-- keeps the hash. The device starts inactive: pair it by hand with
--   update printer.devices set active = true where pairing_code = 'XXXXXX';
create function printer.register_device(name text)
returns jsonb
language plpgsql security definer set search_path = ''
as $$
#variable_conflict use_variable
declare
  alphabet constant text := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';  -- no 0/O, 1/I
  v_token text := encode(extensions.gen_random_bytes(24), 'hex');
  v_code  text;
  v_id    uuid;
begin
  if name is null or name !~ '^[a-z0-9][a-z0-9-]{1,40}$' then
    raise exception 'invalid_name' using hint = 'lowercase letters, digits and dashes';
  end if;
  -- ponytail: global cap, anyone holding the publishable key can call this.
  if (select count(*) from printer.devices d
      where not d.active and d.created_at > now() - interval '1 hour') >= 10 then
    raise exception 'too_many_registrations';
  end if;

  loop
    select string_agg(substr(alphabet, 1 + get_byte(r.b, i) % 32, 1), '' order by i)
      into v_code
      from (select extensions.gen_random_bytes(6) as b) r, generate_series(0, 5) i;
    exit when not exists (select 1 from printer.devices d where d.pairing_code = v_code);
  end loop;

  -- Same name but never paired (e.g. reflashed before pairing): take it over.
  -- A paired name stays taken until its row is deleted.
  insert into printer.devices as d (name, token_hash, pairing_code)
  values (name, printer._hash(v_token), v_code)
  on conflict on constraint devices_name_key do update
    set token_hash = excluded.token_hash,
        pairing_code = excluded.pairing_code,
        created_at = now()
    where not d.active
  returning d.id into v_id;

  if v_id is null then
    raise exception 'name_taken'
      using hint = 'delete from printer.devices where name = ''<name>'';';
  end if;
  return jsonb_build_object('device_id', v_id, 'token', v_token, 'pairing_code', v_code);
end $$;


-- Queue a print. With `device` (name or id) it goes to that device only;
-- without, one job per active device subscribed to `source`.
-- Returns {"jobs": [ids], "rate_limited": [device names skipped]}.
create function printer.send_print(source text, template text, payload jsonb,
                                   device text default null)
returns jsonb
language plpgsql security definer set search_path = ''
as $$
#variable_conflict use_variable
declare
  -- ponytail: one limit for every source; make it a column if sources need different ones.
  source_limit constant int := 60;
  v_dev     record;
  v_payload jsonb;
  v_seen    int;
  v_id      bigint;
  v_jobs    bigint[] := '{}';
  v_skipped text[]   := '{}';
  v_matched int      := 0;
begin
  if source is null or source !~ '^[A-Za-z0-9._:-]{1,64}$' then
    raise exception 'invalid_source' using hint = '1-64 chars: letters, digits . _ : -';
  end if;
  if template is null or template not in ('markdown', 'image', 'slices', 'showmemo') then
    raise exception 'invalid_template' using hint = 'markdown, image, slices or showmemo';
  end if;
  if payload is null or jsonb_typeof(payload) <> 'object' then
    raise exception 'invalid_payload' using hint = 'payload must be a JSON object';
  end if;
  if octet_length(payload::text) > 65536 then
    raise exception 'payload_too_large' using hint = 'send images as image_url, not base64';
  end if;
  if template = 'showmemo' and coalesce(payload ->> 'object_id', '') !~ '^\d+$' then
    raise exception 'invalid_payload' using hint = 'showmemo needs a numeric object_id';
  end if;
  if (select count(*) from printer.jobs j
      where j.source = source and j.created_at > now() - interval '1 hour') >= source_limit then
    raise exception 'rate_limited' using hint = format('max %s jobs per hour per source', source_limit);
  end if;

  for v_dev in
    select d.id, d.name, d.hourly_limit
    from printer.devices d
    where d.active
      and case when device is null then source = any (d.subscriptions)
               else d.name = device or d.id::text = device end
  loop
    v_matched := v_matched + 1;
    if (select count(*) from printer.jobs j
        where j.device_id = v_dev.id and j.created_at > now() - interval '1 hour') >= v_dev.hourly_limit then
      v_skipped := v_skipped || v_dev.name;
      continue;
    end if;

    v_payload := payload;
    if template = 'showmemo' then
      -- How often this printer got this artwork before: the device prints
      -- times_before + 1 strips (2nd download -> 2 strips).
      select count(*) into v_seen
      from printer.jobs j
      where j.device_id = v_dev.id and j.template = 'showmemo'
        and j.payload ->> 'object_id' = payload ->> 'object_id';
      v_payload := payload || jsonb_build_object('times_before', v_seen);
    end if;

    insert into printer.jobs (source, template, payload, device_id)
    values (source, template, v_payload, v_dev.id)
    returning id into v_id;
    v_jobs := v_jobs || v_id;
  end loop;

  if device is not null and v_matched = 0 then
    raise exception 'unknown_device' using hint = 'no active device with that name or id';
  end if;
  return jsonb_build_object('jobs', to_jsonb(v_jobs), 'rate_limited', to_jsonb(v_skipped));
end $$;


-- A device asks for work. Returns {"active", "name", "jobs": [...]}.
-- An unpaired device gets active=false and no jobs (last_seen still updates).
create function printer.claim_jobs(device_token text, max_jobs int default 5)
returns jsonb
language plpgsql security definer set search_path = ''
as $$
#variable_conflict use_variable
declare
  v_dev  printer.devices;
  v_jobs jsonb;
begin
  update printer.devices d set last_seen = now()
  where d.token_hash = printer._hash(device_token)
  returning d.* into v_dev;
  if v_dev.id is null then
    raise exception 'unknown_device' using hint = 'register again';
  end if;
  if not v_dev.active then
    return jsonb_build_object('active', false, 'name', v_dev.name, 'jobs', '[]'::jsonb);
  end if;

  -- Claimed but never finished (crash, power cut mid-print): hand it back
  -- after 5 minutes, give up after 3 attempts so a bad job can't loop.
  update printer.jobs j
  set status = case when j.attempts >= 3 then 'failed' else 'queued' end,
      error  = case when j.attempts >= 3 then 'not finished after 3 attempts' end
  where j.device_id = v_dev.id and j.status = 'printing'
    and j.claimed_at < now() - interval '5 minutes';

  with claimed as (
    update printer.jobs j
    set status = 'printing', claimed_at = now(), attempts = j.attempts + 1
    where j.id in (select q.id from printer.jobs q
                   where q.device_id = v_dev.id and q.status = 'queued'
                   order by q.id
                   limit least(greatest(coalesce(max_jobs, 5), 1), 20)
                   for update skip locked)
    returning j.id, j.created_at, j.source, j.template, j.payload, j.attempts
  )
  select coalesce(jsonb_agg(to_jsonb(c) order by c.id), '[]'::jsonb) into v_jobs from claimed c;

  return jsonb_build_object('active', true, 'name', v_dev.name, 'jobs', v_jobs);
end $$;


-- A device reports a claimed job: error null = printed, else the reason.
-- Returns false if the job isn't this device's or isn't being printed.
create function printer.finish_job(device_token text, job_id bigint, error text default null)
returns boolean
language plpgsql security definer set search_path = ''
as $$
#variable_conflict use_variable
begin
  update printer.jobs j
  set status     = case when error is null then 'done' else 'failed' end,
      printed_at = case when error is null then now() end,
      error      = left(error, 2000)
  where j.id = job_id and j.status = 'printing'
    and j.device_id = (select d.id from printer.devices d
                       where d.token_hash = printer._hash(device_token) and d.active);
  return found;
end $$;


-- Functions are executable by PUBLIC by default in Postgres, and per-schema
-- default privileges can't revoke that. Lock all, then open the four.
-- Any function added to this schema later must be revoked the same way.
revoke all on all functions in schema printer from public, anon, authenticated;
grant execute on function printer.register_device(text)                to anon, authenticated;
grant execute on function printer.send_print(text, text, jsonb, text)  to anon, authenticated;
grant execute on function printer.claim_jobs(text, int)                to anon, authenticated;
grant execute on function printer.finish_job(text, bigint, text)       to anon, authenticated;
