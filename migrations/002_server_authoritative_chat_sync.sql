-- Ask Crump 4.3.2
-- Server-authoritative AI reply persistence + lossless cross-device message merges.

create or replace function public.chat_message_key(p_message jsonb)
returns text
language sql
immutable
set search_path = public
as $$
  select case
    when coalesce(p_message->>'role','') = 'assistant'
      and coalesce(nullif(p_message->>'inReplyTo',''), nullif(p_message->>'in_reply_to','')) is not null
      then 'reply:' || coalesce(nullif(p_message->>'inReplyTo',''), nullif(p_message->>'in_reply_to',''))
    when nullif(p_message->>'id','') is not null
      then 'id:' || (p_message->>'id')
    else 'legacy:' || coalesce(p_message->>'role','') || ':' || coalesce(p_message->>'timestamp','') || ':' || left(coalesce(p_message->>'content',''), 240)
  end;
$$;

create or replace function public.merge_chat_messages(p_existing jsonb, p_incoming jsonb)
returns jsonb
language plpgsql
immutable
set search_path = public
as $$
declare
  result jsonb := case when jsonb_typeof(coalesce(p_existing, '[]'::jsonb)) = 'array' then coalesce(p_existing, '[]'::jsonb) else '[]'::jsonb end;
  incoming_messages jsonb := case when jsonb_typeof(coalesce(p_incoming, '[]'::jsonb)) = 'array' then coalesce(p_incoming, '[]'::jsonb) else '[]'::jsonb end;
  incoming_item jsonb;
  existing_item jsonb;
  merged_item jsonb;
  incoming_key text;
  existing_key text;
  i integer;
  matched boolean;
  existing_delivery_rank integer;
  incoming_delivery_rank integer;
  existing_reply_rank integer;
  incoming_reply_rank integer;
begin
  for incoming_item in select value from jsonb_array_elements(incoming_messages)
  loop
    incoming_key := public.chat_message_key(incoming_item);
    matched := false;

    if jsonb_array_length(result) > 0 then
      for i in 0..jsonb_array_length(result)-1
      loop
        existing_item := result->i;
        existing_key := public.chat_message_key(existing_item);
        if existing_key = incoming_key then
          merged_item := existing_item || incoming_item;

          if coalesce(existing_item->>'role', incoming_item->>'role', '') = 'user' then
            existing_delivery_rank := case coalesce(existing_item->>'deliveryStatus', existing_item->>'delivery_status', '')
              when 'sending' then 1 when 'queued' then 2 when 'failed' then 2 when 'delivered' then 3 when 'seen' then 4 else 0 end;
            incoming_delivery_rank := case coalesce(incoming_item->>'deliveryStatus', incoming_item->>'delivery_status', '')
              when 'sending' then 1 when 'queued' then 2 when 'failed' then 2 when 'delivered' then 3 when 'seen' then 4 else 0 end;
            if existing_delivery_rank > incoming_delivery_rank then
              merged_item := merged_item || jsonb_build_object('deliveryStatus', coalesce(existing_item->>'deliveryStatus', existing_item->>'delivery_status'));
            end if;

            existing_reply_rank := case coalesce(existing_item->>'replyStatus', existing_item->>'reply_status', '')
              when 'pending' then 1 when 'failed' then 2 when 'processing' then 3 when 'replied' then 4 else 0 end;
            incoming_reply_rank := case coalesce(incoming_item->>'replyStatus', incoming_item->>'reply_status', '')
              when 'pending' then 1 when 'failed' then 2 when 'processing' then 3 when 'replied' then 4 else 0 end;
            if existing_reply_rank > incoming_reply_rank then
              merged_item := merged_item || jsonb_build_object('replyStatus', coalesce(existing_item->>'replyStatus', existing_item->>'reply_status'));
            end if;
          end if;

          result := jsonb_set(result, array[i::text], merged_item, false);
          matched := true;
          exit;
        end if;
      end loop;
    end if;

    if not matched then
      result := result || jsonb_build_array(incoming_item);
    end if;
  end loop;

  return result;
end;
$$;

create or replace function public.apply_chat_sync(
  p_user_id uuid,
  p_chat_id uuid,
  p_title text,
  p_messages jsonb,
  p_created_at timestamptz,
  p_updated_at timestamptz,
  p_deleted_at timestamptz,
  p_revision bigint
)
returns table(accepted boolean, resulting_revision bigint)
language plpgsql
security definer
set search_path = public
as $$
declare
  applied_revision bigint;
begin
  insert into public.user_chats as current_chat(user_id, chat_id, title, messages, created_at, updated_at, deleted_at, revision)
  values(
    p_user_id,
    p_chat_id,
    coalesce(nullif(p_title,''), 'New conversation'),
    coalesce(p_messages, '[]'::jsonb),
    coalesce(p_created_at, p_updated_at, now()),
    coalesce(p_updated_at, now()),
    p_deleted_at,
    greatest(1, coalesce(p_revision,1))
  )
  on conflict(user_id, chat_id) do update set
    title = case when excluded.updated_at >= current_chat.updated_at then excluded.title else current_chat.title end,
    messages = case
      when excluded.deleted_at is not null and excluded.updated_at >= current_chat.updated_at then '[]'::jsonb
      else public.merge_chat_messages(current_chat.messages, excluded.messages)
    end,
    deleted_at = case when excluded.updated_at >= current_chat.updated_at then excluded.deleted_at else current_chat.deleted_at end,
    created_at = least(current_chat.created_at, excluded.created_at),
    updated_at = greatest(current_chat.updated_at, excluded.updated_at, now()),
    revision = greatest(excluded.revision, current_chat.revision + 1)
  where
    excluded.updated_at > current_chat.updated_at
    or (excluded.updated_at = current_chat.updated_at and excluded.revision > current_chat.revision)
    or (
      current_chat.deleted_at is null
      and excluded.deleted_at is null
      and public.merge_chat_messages(current_chat.messages, excluded.messages) <> current_chat.messages
    )
  returning current_chat.revision into applied_revision;

  if found then
    return query select true, applied_revision;
  else
    select revision into applied_revision from public.user_chats where user_id = p_user_id and chat_id = p_chat_id;
    return query select false, coalesce(applied_revision, 1);
  end if;
end;
$$;

create or replace function public.persist_chat_reply(
  p_user_id uuid,
  p_chat_id uuid,
  p_title text,
  p_user_message jsonb,
  p_assistant_message jsonb
)
returns table(resulting_revision bigint, resulting_updated_at timestamptz)
language plpgsql
security definer
set search_path = public
as $$
declare
  current_messages jsonb;
  merged_messages jsonb := '[]'::jsonb;
  current_revision bigint;
  current_title text;
  item jsonb;
  safe_user_message jsonb := coalesce(p_user_message, '{}'::jsonb);
  safe_assistant_message jsonb := coalesce(p_assistant_message, '{}'::jsonb);
  user_message_id text := nullif(p_user_message->>'id', '');
  assistant_message_id text := nullif(p_assistant_message->>'id', '');
  user_found boolean := false;
  assistant_found boolean := false;
  new_updated_at timestamptz := now();
begin
  if user_message_id is null or assistant_message_id is null then raise exception 'message ids are required'; end if;
  if coalesce(p_user_message->>'role', '') <> 'user' then raise exception 'p_user_message must have role=user'; end if;
  if coalesce(p_assistant_message->>'role', '') <> 'assistant' then raise exception 'p_assistant_message must have role=assistant'; end if;

  if not (safe_user_message ? 'timestamp') then safe_user_message := safe_user_message || jsonb_build_object('timestamp', new_updated_at); end if;
  if not (safe_assistant_message ? 'timestamp') then safe_assistant_message := safe_assistant_message || jsonb_build_object('timestamp', new_updated_at); end if;

  insert into public.user_chats(user_id, chat_id, title, messages, created_at, updated_at, revision, deleted_at)
  values(p_user_id, p_chat_id, coalesce(nullif(p_title, ''), 'New conversation'), '[]'::jsonb, now(), now(), 1, null)
  on conflict(user_id, chat_id) do nothing;

  select messages, revision, title into current_messages, current_revision, current_title
  from public.user_chats
  where user_id = p_user_id and chat_id = p_chat_id
  for update;

  current_messages := coalesce(current_messages, '[]'::jsonb);
  current_revision := greatest(1, coalesce(current_revision, 1));

  for item in select value from jsonb_array_elements(current_messages)
  loop
    if item->>'id' = user_message_id then
      item := item || (safe_user_message - 'timestamp');
      user_found := true;
    elsif item->>'role' = 'assistant'
      and (item->>'id' = assistant_message_id or item->>'inReplyTo' = user_message_id or item->>'in_reply_to' = user_message_id) then
      item := item || safe_assistant_message;
      assistant_found := true;
    end if;
    merged_messages := merged_messages || jsonb_build_array(item);
  end loop;

  if not user_found then merged_messages := merged_messages || jsonb_build_array(safe_user_message); end if;
  if not assistant_found then merged_messages := merged_messages || jsonb_build_array(safe_assistant_message); end if;

  update public.user_chats
  set title = coalesce(nullif(p_title, ''), current_title, 'New conversation'),
      messages = merged_messages,
      deleted_at = null,
      updated_at = new_updated_at,
      revision = current_revision + 1
  where user_id = p_user_id and chat_id = p_chat_id;

  return query select current_revision + 1, new_updated_at;
end;
$$;

revoke all on function public.chat_message_key(jsonb) from public, anon, authenticated;
revoke all on function public.merge_chat_messages(jsonb, jsonb) from public, anon, authenticated;
revoke all on function public.apply_chat_sync(uuid, uuid, text, jsonb, timestamptz, timestamptz, timestamptz, bigint) from public, anon, authenticated;
revoke all on function public.persist_chat_reply(uuid, uuid, text, jsonb, jsonb) from public, anon, authenticated;

grant execute on function public.chat_message_key(jsonb) to service_role;
grant execute on function public.merge_chat_messages(jsonb, jsonb) to service_role;
grant execute on function public.apply_chat_sync(uuid, uuid, text, jsonb, timestamptz, timestamptz, timestamptz, bigint) to service_role;
grant execute on function public.persist_chat_reply(uuid, uuid, text, jsonb, jsonb) to service_role;
