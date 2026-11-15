-- Smoke test for the printer schema, run as the real caller (anon).
-- Run it in the SQL editor. It always ends with an exception, which rolls
-- everything back; the message lists each check. Any "FAIL" is a bug.
do $$
declare
  log text := '';
  d jsonb; d2 jsonb; tok text; r jsonb; ids bigint[];
  ok boolean;
begin
  set local role anon;

  -- 1. back room is closed
  begin perform 1 from printer.jobs;    log := log || 'FAIL jobs readable | ';    exception when insufficient_privilege then log := log || 'ok jobs denied | '; end;
  begin perform 1 from printer.devices; log := log || 'FAIL devices readable | '; exception when insufficient_privilege then log := log || 'ok devices denied | '; end;
  begin perform printer._hash('x');     log := log || 'FAIL _hash callable | ';   exception when insufficient_privilege then log := log || 'ok _hash denied | '; end;

  -- 2. register -> inactive
  d := printer.register_device('test-printer');
  tok := d->>'token';
  r := printer.claim_jobs(tok);
  log := log || format('inactive claim active=%s | ', r->>'active');
  begin perform printer.send_print('test', 'markdown', '{"body":"hi"}', 'test-printer'); log := log || 'FAIL inactive got job | ';
  exception when others then log := log || format('ok inactive send -> %s | ', sqlerrm); end;

  -- 3. pair (as owner), then queue
  reset role;
  update printer.devices set active = true, subscriptions = '{showmemo}', hourly_limit = 3 where pairing_code = d->>'pairing_code';
  set local role anon;

  r := printer.send_print('showmemo', 'showmemo', '{"object_id":13802,"image_url":"https://x/y.jpg"}');
  r := printer.send_print('showmemo', 'showmemo', '{"object_id":13802,"image_url":"https://x/y.jpg"}');
  r := printer.send_print('test', 'markdown', '{"body":"# hi"}', 'test-printer');
  r := printer.send_print('test', 'markdown', '{"body":"# hi"}', 'test-printer');
  log := log || format('4th send (cap 3) rate_limited=%s | ', r->'rate_limited');

  -- 4. claim + finish
  r := printer.claim_jobs(tok);
  select array_agg((j->>'id')::bigint order by (j->>'id')::bigint) into ids from jsonb_array_elements(r->'jobs') j;
  log := log || format('claimed=%s (want 3) times_before=%s (want 0,1) | ', jsonb_array_length(r->'jobs'),
    (select string_agg(j->'payload'->>'times_before', ',') from jsonb_array_elements(r->'jobs') j where j->>'template' = 'showmemo'));
  log := log || format('claim again=%s (want 0) | ', jsonb_array_length(printer.claim_jobs(tok)->'jobs'));
  ok := printer.finish_job(tok, ids[1], null);           log := log || format('finish=%s (want t) | ', ok);
  ok := printer.finish_job(tok, ids[2], 'paper out');    log := log || format('finish err=%s (want t) | ', ok);
  ok := printer.finish_job(tok, ids[1], null);           log := log || format('finish twice=%s (want f) | ', ok);
  ok := printer.finish_job('wrong-token', ids[3], null); log := log || format('wrong token=%s (want f) | ', ok);

  -- 5. validation
  begin perform printer.send_print('test', 'bogus', '{}'); exception when others then log := log || format('%s | ', sqlerrm); end;
  begin perform printer.send_print('bad source!', 'markdown', '{}'); exception when others then log := log || format('%s | ', sqlerrm); end;
  begin perform printer.send_print('test', 'showmemo', '{"title":"x"}'); exception when others then log := log || format('%s | ', sqlerrm); end;
  begin perform printer.send_print('test', 'image', jsonb_build_object('b', repeat('x', 70000))); exception when others then log := log || format('%s | ', sqlerrm); end;
  begin perform printer.send_print('test', 'markdown', '{}', 'nope'); exception when others then log := log || format('%s | ', sqlerrm); end;
  begin perform printer.register_device('test-printer'); exception when others then log := log || format('%s | ', sqlerrm); end;
  d2 := printer.register_device('test-other');
  d2 := printer.register_device('test-other');
  log := log || format('reregister unpaired ok=%s', d2 ? 'token');

  raise exception 'RESULT: %', log;
end $$;
