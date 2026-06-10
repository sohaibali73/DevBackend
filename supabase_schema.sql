--
-- PostgreSQL database dump
--

\restrict XSX3LOX4kX6orljnHHPsN4aryCbatg347kcYzeFJQ321sBQelCBdvf9BPqZ9Ymk

-- Dumped from database version 17.6
-- Dumped by pg_dump version 17.10 (Debian 17.10-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


--
-- Name: pptx_asset_scope; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.pptx_asset_scope AS ENUM (
    'global',
    'org',
    'user'
);


--
-- Name: _pptx_assets_touch(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public._pptx_assets_touch() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


--
-- Name: _pptx_programs_touch(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public._pptx_programs_touch() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


--
-- Name: audit_log_trigger(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.audit_log_trigger() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_logs (user_id, action, resource_type, resource_id, new_values)
        VALUES (auth.uid(), 'INSERT', TG_TABLE_NAME, NEW.id::text, to_jsonb(NEW));
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_logs (user_id, action, resource_type, resource_id, old_values, new_values)
        VALUES (auth.uid(), 'UPDATE', TG_TABLE_NAME, NEW.id::text, to_jsonb(OLD), to_jsonb(NEW));
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit_logs (user_id, action, resource_type, resource_id, old_values)
        VALUES (auth.uid(), 'DELETE', TG_TABLE_NAME, OLD.id::text, to_jsonb(OLD));
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: handle_new_user(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.handle_new_user() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
BEGIN
    INSERT INTO public.user_profiles (id, email, name, nickname)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(
            NEW.raw_user_meta_data->>'name',
            NEW.raw_user_meta_data->>'full_name',
            split_part(NEW.email, '@', 1)
        ),
        split_part(NEW.email, '@', 1)
    );
    RETURN NEW;
END;
$$;


--
-- Name: match_brain_chunks(public.vector, double precision, integer, uuid, text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.match_brain_chunks(query_embedding public.vector, match_threshold double precision DEFAULT 0.4, match_count integer DEFAULT 8, p_user_id uuid DEFAULT NULL::uuid, p_category text DEFAULT NULL::text) RETURNS TABLE(chunk_id uuid, document_id uuid, title text, filename text, category text, chunk_index integer, content text, similarity double precision)
    LANGUAGE sql STABLE
    AS $$
    SELECT
        bc.id                       AS chunk_id,
        bc.document_id,
        bd.title::text              AS title,
        bd.filename::text           AS filename,
        bd.category::text           AS category,
        bc.chunk_index,
        bc.content,
        1 - (bc.embedding <=> query_embedding) AS similarity
    FROM brain_chunks bc
    JOIN brain_documents bd ON bd.id = bc.document_id
    WHERE bc.embedding IS NOT NULL
      AND (p_user_id  IS NULL OR bd.uploaded_by = p_user_id)
      AND (p_category IS NULL OR bd.category    = p_category)
      AND 1 - (bc.embedding <=> query_embedding) >= match_threshold
    ORDER BY bc.embedding <=> query_embedding
    LIMIT match_count;
$$;


--
-- Name: match_conversation_file_chunks(uuid, public.vector, double precision, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.match_conversation_file_chunks(p_conversation_id uuid, query_embedding public.vector, match_threshold double precision DEFAULT 0.4, match_count integer DEFAULT 8) RETURNS TABLE(chunk_id uuid, file_id uuid, filename text, chunk_index integer, content text, similarity double precision)
    LANGUAGE sql STABLE
    AS $$
    SELECT
        fc.id          AS chunk_id,
        fc.file_id,
        fu.original_filename AS filename,
        fc.chunk_index,
        fc.content,
        1 - (fc.embedding <=> query_embedding) AS similarity
    FROM file_chunks fc
    JOIN conversation_files cf ON cf.file_id = fc.file_id
    JOIN file_uploads       fu ON fu.id      = fc.file_id
    WHERE cf.conversation_id = p_conversation_id
      AND fc.embedding IS NOT NULL
      AND 1 - (fc.embedding <=> query_embedding) >= match_threshold
    ORDER BY fc.embedding <=> query_embedding
    LIMIT match_count;
$$;


--
-- Name: match_memories(public.vector, double precision, integer, uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.match_memories(query_embedding public.vector, match_threshold double precision, match_count integer, p_user_id uuid) RETURNS TABLE(id bigint, key text, value jsonb, kind text, tags text[], updated_at timestamp with time zone, similarity double precision)
    LANGUAGE sql STABLE
    AS $$
    SELECT m.id, m.key, m.value, m.kind, m.tags, m.updated_at,
           1 - (m.embedding <=> query_embedding) AS similarity
    FROM   memories m
    WHERE  m.user_id = p_user_id
      AND  m.embedding IS NOT NULL
      AND  1 - (m.embedding <=> query_embedding) >= match_threshold
    ORDER  BY m.embedding <=> query_embedding
    LIMIT  match_count;
$$;


--
-- Name: match_stack_chunks(uuid, public.vector, double precision, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.match_stack_chunks(p_stack_id uuid, query_embedding public.vector, match_threshold double precision DEFAULT 0.5, match_count integer DEFAULT 20) RETURNS TABLE(chunk_id uuid, document_id uuid, chunk_index integer, content text, similarity double precision)
    LANGUAGE sql STABLE
    AS $$
    SELECT
        bc.id AS chunk_id,
        bc.document_id,
        bc.chunk_index,
        bc.content,
        1 - (bc.embedding <=> query_embedding) AS similarity
    FROM brain_chunks bc
    JOIN brain_documents bd ON bd.id = bc.document_id
    WHERE bd.stack_id = p_stack_id
      AND bc.embedding IS NOT NULL
      AND 1 - (bc.embedding <=> query_embedding) >= match_threshold
    ORDER BY bc.embedding <=> query_embedding
    LIMIT match_count;
$$;


--
-- Name: refresh_knowledge_stack_stats(uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.refresh_knowledge_stack_stats(p_stack_id uuid) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF p_stack_id IS NULL THEN
        RETURN;
    END IF;

    UPDATE knowledge_stacks ks
    SET
        document_count = COALESCE(s.doc_count, 0),
        total_chunks = COALESCE(s.chunk_total, 0),
        total_size_bytes = COALESCE(s.size_total, 0),
        updated_at = NOW()
    FROM (
        SELECT
            COUNT(*) AS doc_count,
            COALESCE(SUM(chunk_count), 0) AS chunk_total,
            COALESCE(SUM(file_size), 0) AS size_total
        FROM brain_documents
        WHERE stack_id = p_stack_id
    ) s
    WHERE ks.id = p_stack_id;
END;
$$;


--
-- Name: refresh_studio_writing_style_stats(uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.refresh_studio_writing_style_stats(p_style_id uuid) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF p_style_id IS NULL THEN
        RETURN;
    END IF;

    UPDATE studio_writing_styles ws
    SET
        sample_count = COALESCE(s.cnt, 0),
        total_words  = COALESCE(s.words, 0),
        updated_at   = NOW()
    FROM (
        SELECT
            COUNT(*)               AS cnt,
            COALESCE(SUM(word_count), 0) AS words
        FROM studio_writing_style_samples
        WHERE style_id = p_style_id
    ) s
    WHERE ws.id = p_style_id;
END;
$$;


--
-- Name: set_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;


--
-- Name: trg_brain_documents_stack_stats(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.trg_brain_documents_stack_stats() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Refresh stats for the OLD stack (if doc was reassigned/deleted)
    IF TG_OP IN ('UPDATE', 'DELETE') AND OLD.stack_id IS NOT NULL THEN
        PERFORM refresh_knowledge_stack_stats(OLD.stack_id);
    END IF;

    -- Refresh stats for the NEW stack (if doc was added/reassigned)
    IF TG_OP IN ('INSERT', 'UPDATE') AND NEW.stack_id IS NOT NULL THEN
        PERFORM refresh_knowledge_stack_stats(NEW.stack_id);
    END IF;

    RETURN COALESCE(NEW, OLD);
END;
$$;


--
-- Name: trg_knowledge_stacks_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.trg_knowledge_stacks_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


--
-- Name: trg_published_sites_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.trg_published_sites_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


--
-- Name: trg_studio_artifacts_touch_project(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.trg_studio_artifacts_touch_project() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE studio_projects
    SET updated_at = NOW()
    WHERE id = NEW.project_id;
    RETURN NEW;
END;
$$;


--
-- Name: trg_studio_projects_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.trg_studio_projects_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


--
-- Name: trg_studio_writing_style_samples_stats(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.trg_studio_writing_style_samples_stats() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP IN ('UPDATE','DELETE') AND OLD.style_id IS NOT NULL THEN
        PERFORM refresh_studio_writing_style_stats(OLD.style_id);
    END IF;
    IF TG_OP IN ('INSERT','UPDATE') AND NEW.style_id IS NOT NULL THEN
        PERFORM refresh_studio_writing_style_stats(NEW.style_id);
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$;


--
-- Name: trg_studio_writing_styles_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.trg_studio_writing_styles_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


--
-- Name: update_brain_search_vector(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_brain_search_vector() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.search_vector := 
        setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.summary, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.raw_content, '')), 'C');
    RETURN NEW;
END;
$$;


--
-- Name: update_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


--
-- Name: user_skills_set_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.user_skills_set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


--
-- Name: workspace_files_touch_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.workspace_files_touch_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: afl_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.afl_codes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    title text NOT NULL,
    description text,
    code text NOT NULL,
    strategy_type text DEFAULT 'standalone'::text,
    tags text[] DEFAULT '{}'::text[],
    is_valid boolean,
    validation_errors text[],
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    metadata jsonb DEFAULT '{}'::jsonb,
    feedback text
);


--
-- Name: afl_feedback; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.afl_feedback (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    generation_id text NOT NULL,
    feedback text NOT NULL,
    comment text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT afl_feedback_feedback_check CHECK ((feedback = ANY (ARRAY['positive'::text, 'negative'::text])))
);


--
-- Name: afl_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.afl_history (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    action text NOT NULL,
    input_prompt text,
    input_code text,
    output_code text,
    output_explanation text,
    model text,
    tokens_used integer,
    created_at timestamp with time zone DEFAULT now(),
    feedback text,
    CONSTRAINT afl_history_action_check CHECK ((action = ANY (ARRAY['generate'::text, 'debug'::text, 'validate'::text, 'explain'::text])))
);


--
-- Name: agent_inter_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_inter_messages (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    team_id uuid,
    from_agent_id text NOT NULL,
    to_agent_id text,
    content text NOT NULL,
    message_type text DEFAULT 'question'::text,
    requires_response boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: agent_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_messages (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    team_id uuid NOT NULL,
    from_role text NOT NULL,
    to_role text,
    content text NOT NULL,
    message_type text DEFAULT 'message'::text NOT NULL,
    metadata jsonb,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT agent_messages_message_type_check CHECK ((message_type = ANY (ARRAY['task'::text, 'question'::text, 'answer'::text, 'critique'::text, 'synthesis'::text, 'sandbox_result'::text, 'message'::text])))
);


--
-- Name: agent_team_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_team_members (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    team_id uuid NOT NULL,
    role text NOT NULL,
    model_id text NOT NULL,
    provider text DEFAULT 'anthropic'::text NOT NULL,
    instructions text,
    color text DEFAULT '#FEC00F'::text,
    created_at timestamp with time zone DEFAULT now(),
    agent_id text,
    nickname text,
    custom_role_desc text DEFAULT ''::text,
    capabilities jsonb DEFAULT '[]'::jsonb,
    can_collaborate_with jsonb DEFAULT '[]'::jsonb,
    CONSTRAINT agent_team_members_role_check CHECK ((role = ANY (ARRAY['leader'::text, 'researcher'::text, 'analyst'::text, 'critic'::text, 'synthesizer'::text, 'coder'::text])))
);


--
-- Name: agent_teams; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_teams (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    name text DEFAULT 'New Team'::text NOT NULL,
    description text,
    status text DEFAULT 'idle'::text NOT NULL,
    task text,
    result jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    workflow_mode text DEFAULT 'hybrid'::text,
    allow_inter_agent_chat boolean DEFAULT true,
    CONSTRAINT agent_teams_status_check CHECK ((status = ANY (ARRAY['idle'::text, 'working'::text, 'completed'::text, 'failed'::text])))
);


--
-- Name: app_api_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.app_api_keys (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    name text NOT NULL,
    key_hash text NOT NULL,
    key_prefix text NOT NULL,
    permissions text[] DEFAULT '{read,write}'::text[] NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    last_used_at timestamp with time zone
);


--
-- Name: attachments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.attachments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    conversation_id uuid,
    user_id uuid NOT NULL,
    filename text NOT NULL,
    size integer,
    mime_type text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    action text NOT NULL,
    resource_type text,
    resource_id text,
    ip_address inet,
    user_agent text,
    old_values jsonb,
    new_values jsonb,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: backtest_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.backtest_results (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    strategy_name text NOT NULL,
    backtest_config jsonb,
    results jsonb,
    performance_metrics jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: brain_chunks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.brain_chunks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    document_id uuid NOT NULL,
    chunk_index integer DEFAULT 0 NOT NULL,
    content text NOT NULL,
    embedding public.vector(1024),
    token_count integer,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: brain_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.brain_documents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    uploaded_by uuid,
    title character varying(500) NOT NULL,
    filename character varying(500),
    file_type character varying(100),
    file_size bigint DEFAULT 0,
    category character varying(100) DEFAULT 'general'::character varying,
    subcategories jsonb DEFAULT '[]'::jsonb,
    tags jsonb DEFAULT '[]'::jsonb,
    raw_content text,
    summary text,
    content_hash character varying(64),
    source_type character varying(50) DEFAULT 'upload'::character varying,
    is_processed boolean DEFAULT false,
    chunk_count integer DEFAULT 0,
    processed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    storage_path text DEFAULT ''::text,
    stack_id uuid
);


--
-- Name: conversation_files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversation_files (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    conversation_id uuid NOT NULL,
    file_id uuid NOT NULL,
    purpose text DEFAULT 'reference'::text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: conversation_focus; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversation_focus (
    conversation_id uuid NOT NULL,
    user_id uuid NOT NULL,
    focus jsonb DEFAULT '{}'::jsonb NOT NULL,
    turns_since_llm_polish integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE conversation_focus; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.conversation_focus IS 'Rolling focus chain per conversation: goal, open tasks, key files, decisions. Updated deterministically each turn; optionally LLM-polished every 5 turns in the background.';


--
-- Name: conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    title text,
    summary text,
    system_prompt text,
    model text DEFAULT 'claude-sonnet-4-20250514'::text,
    is_archived boolean DEFAULT false,
    is_pinned boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    total_tokens_used integer DEFAULT 0,
    metadata jsonb DEFAULT '{}'::jsonb,
    conversation_type text DEFAULT 'chat'::text,
    sandbox_session_id uuid DEFAULT gen_random_uuid() NOT NULL
);


--
-- Name: messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.messages (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    conversation_id uuid NOT NULL,
    role text NOT NULL,
    content text NOT NULL,
    input_tokens integer DEFAULT 0,
    output_tokens integer DEFAULT 0,
    tool_calls jsonb,
    tool_results jsonb,
    created_at timestamp with time zone DEFAULT now(),
    metadata jsonb DEFAULT '{}'::jsonb,
    parts jsonb,
    execution_id text,
    sandbox_language text,
    display_type text,
    CONSTRAINT messages_role_check CHECK ((role = ANY (ARRAY['user'::text, 'assistant'::text, 'system'::text])))
);


--
-- Name: COLUMN messages.parts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.messages.parts IS 'AI SDK v4 message parts array. Format: [{type:"text",text:"..."},{type:"tool-invocation",toolCallId:"...",toolName:"...",state:"result",result:{...}}]. Enables frontend to reconstruct Generative UI cards from conversation history.';


--
-- Name: conversation_summaries; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.conversation_summaries AS
 SELECT c.id,
    c.title,
    c.sandbox_session_id,
    c.created_at,
    c.updated_at,
    c.user_id,
    m.content AS last_message,
    m.created_at AS last_message_at
   FROM (public.conversations c
     LEFT JOIN LATERAL ( SELECT messages.content,
            messages.created_at
           FROM public.messages
          WHERE (messages.conversation_id = c.id)
          ORDER BY messages.created_at DESC
         LIMIT 1) m ON (true));


--
-- Name: courses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.courses (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    title text NOT NULL,
    description text,
    level text DEFAULT 'beginner'::text NOT NULL,
    duration integer DEFAULT 60 NOT NULL,
    thumbnail_url text,
    lessons jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT courses_level_check CHECK ((level = ANY (ARRAY['beginner'::text, 'intermediate'::text, 'advanced'::text])))
);


--
-- Name: file_chunks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.file_chunks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    file_id uuid NOT NULL,
    chunk_index integer NOT NULL,
    content text NOT NULL,
    embedding public.vector(1024),
    token_count integer,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: file_uploads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.file_uploads (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    bucket_id text NOT NULL,
    storage_path text NOT NULL,
    original_filename text NOT NULL,
    content_type text,
    file_size integer,
    content_hash text,
    status text DEFAULT 'uploaded'::text,
    error_message text,
    extracted_text text,
    created_at timestamp with time zone DEFAULT now(),
    processed_at timestamp with time zone,
    metadata jsonb DEFAULT '{}'::jsonb,
    CONSTRAINT file_uploads_status_check CHECK ((status = ANY (ARRAY['uploaded'::text, 'processing'::text, 'ready'::text, 'error'::text])))
);


--
-- Name: generated_files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.generated_files (
    file_id text NOT NULL,
    filename text NOT NULL,
    file_type text DEFAULT ''::text NOT NULL,
    size_kb double precision DEFAULT 0 NOT NULL,
    tool_name text DEFAULT ''::text NOT NULL,
    storage_path text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    user_id uuid,
    tool_result_id uuid
);


--
-- Name: TABLE generated_files; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.generated_files IS 'Metadata for every AI-generated file (DOCX, PPTX, XLSX, PDF, CSV). Actual bytes live in Supabase Storage bucket "user-uploads" at path {file_id}/{filename} (or "generated-files" for new uploads). Referenced by core/file_store.py which upserts on conflict(file_id).';


--
-- Name: goal_steps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.goal_steps (
    id bigint NOT NULL,
    goal_id uuid NOT NULL,
    user_id uuid NOT NULL,
    idx integer NOT NULL,
    kind text NOT NULL,
    content jsonb NOT NULL,
    ts timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: goal_steps_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.goal_steps_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: goal_steps_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.goal_steps_id_seq OWNED BY public.goal_steps.id;


--
-- Name: goals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.goals (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    title text NOT NULL,
    description text,
    prompt text NOT NULL,
    status text DEFAULT 'queued'::text NOT NULL,
    plan_jsonb jsonb,
    conversation_id uuid,
    last_note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: knowledge_stacks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.knowledge_stacks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id text NOT NULL,
    name text NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    icon text DEFAULT '📚'::text NOT NULL,
    color text DEFAULT '#6366f1'::text NOT NULL,
    settings jsonb DEFAULT '{"overlap": 150, "load_mode": "static", "chunk_size": 1500, "chunk_count": 20, "generate_embeddings": true}'::jsonb NOT NULL,
    document_count integer DEFAULT 0 NOT NULL,
    total_chunks integer DEFAULT 0 NOT NULL,
    total_size_bytes bigint DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: learnings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.learnings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    document_id uuid,
    user_id uuid,
    title character varying(500),
    content text,
    category character varying(100) DEFAULT 'general'::character varying,
    tags jsonb DEFAULT '[]'::jsonb,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: memories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memories (
    id bigint NOT NULL,
    user_id uuid NOT NULL,
    kind text DEFAULT 'fact'::text NOT NULL,
    key text NOT NULL,
    value jsonb NOT NULL,
    embedding public.vector(1024),
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    source_goal_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: memories_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.memories_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: memories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.memories_id_seq OWNED BY public.memories.id;


--
-- Name: pptx_assets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pptx_assets (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    scope public.pptx_asset_scope NOT NULL,
    owner_id uuid,
    key text NOT NULL,
    kind text NOT NULL,
    file_path text NOT NULL,
    file_sha text NOT NULL,
    mime text NOT NULL,
    aspect numeric,
    bytes_size integer,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    use_when text,
    on_colors text[] DEFAULT '{}'::text[] NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: pptx_program_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pptx_program_versions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    program_id uuid NOT NULL,
    version integer NOT NULL,
    title text,
    canvas jsonb,
    program jsonb NOT NULL,
    patches jsonb,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: pptx_programs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pptx_programs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    title text DEFAULT 'Untitled'::text NOT NULL,
    canvas jsonb DEFAULT '{"preset": "wide"}'::jsonb NOT NULL,
    program jsonb NOT NULL,
    asset_snapshot jsonb DEFAULT '{}'::jsonb NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    file_id text,
    last_render_sha text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: presentations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.presentations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    storage_path text,
    title text NOT NULL,
    slide_count integer,
    prompt text,
    status text DEFAULT 'generated'::text,
    error_message text,
    created_at timestamp with time zone DEFAULT now(),
    metadata jsonb DEFAULT '{}'::jsonb,
    CONSTRAINT presentations_status_check CHECK ((status = ANY (ARRAY['generating'::text, 'generated'::text, 'error'::text])))
);


--
-- Name: published_sites; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.published_sites (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    project_id uuid NOT NULL,
    artifact_id uuid NOT NULL,
    subdomain text NOT NULL,
    custom_domain text,
    site_root_path text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    published_at timestamp with time zone DEFAULT now() NOT NULL,
    last_request_at timestamp with time zone,
    request_count bigint DEFAULT 0 NOT NULL,
    meta jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT published_sites_subdomain_format CHECK ((subdomain ~ '^[a-z0-9](?:[a-z0-9-]{1,30}[a-z0-9])?$'::text))
);


--
-- Name: TABLE published_sites; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.published_sites IS 'Content Studio site publications — public subdomains for AI-generated websites';


--
-- Name: quiz_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.quiz_results (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    quiz_id uuid NOT NULL,
    score double precision NOT NULL,
    passed boolean DEFAULT false NOT NULL,
    answers jsonb DEFAULT '{}'::jsonb NOT NULL,
    submitted_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: quizzes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.quizzes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_id uuid,
    lesson_id text,
    title text NOT NULL,
    passing_score double precision DEFAULT 70.0 NOT NULL,
    questions jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: reverse_analyses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reverse_analyses (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    image_path text,
    description text,
    status text DEFAULT 'processing'::text NOT NULL,
    progress integer DEFAULT 0 NOT NULL,
    patterns jsonb,
    strategy jsonb,
    confidence double precision,
    error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT reverse_analyses_status_check CHECK ((status = ANY (ARRAY['processing'::text, 'completed'::text, 'failed'::text])))
);


--
-- Name: scheduled_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scheduled_jobs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    name text NOT NULL,
    cron text NOT NULL,
    prompt text NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    timezone text DEFAULT 'UTC'::text NOT NULL,
    last_run_at timestamp with time zone,
    next_run_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: studio_artifacts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.studio_artifacts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    user_id uuid NOT NULL,
    conversation_id uuid,
    message_id uuid,
    source_file_id text,
    kind text NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    filename text NOT NULL,
    volume_path text NOT NULL,
    size_bytes bigint DEFAULT 0 NOT NULL,
    slide_count integer,
    page_count integer,
    edit_state jsonb,
    meta jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    file_count integer,
    CONSTRAINT studio_artifacts_kind_check CHECK ((kind = ANY (ARRAY['pptx'::text, 'docx'::text, 'site'::text])))
);


--
-- Name: TABLE studio_artifacts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.studio_artifacts IS 'Versioned PPTX/DOCX outputs for Content Studio projects (bytes on Railway volume)';


--
-- Name: studio_humanization_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.studio_humanization_runs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    project_id uuid,
    conversation_id uuid,
    style_profile_id uuid,
    intensity text DEFAULT 'standard'::text NOT NULL,
    seo_target text,
    preserve_facts boolean DEFAULT true NOT NULL,
    input_text text NOT NULL,
    output_text text DEFAULT ''::text NOT NULL,
    input_word_count integer DEFAULT 0 NOT NULL,
    output_word_count integer DEFAULT 0 NOT NULL,
    final_scores jsonb DEFAULT '{}'::jsonb NOT NULL,
    passes_summary jsonb DEFAULT '[]'::jsonb NOT NULL,
    detector_retries integer DEFAULT 0 NOT NULL,
    volume_path text,
    status text DEFAULT 'pending'::text NOT NULL,
    error text,
    duration_ms integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT studio_humanization_runs_intensity_check CHECK ((intensity = ANY (ARRAY['light'::text, 'standard'::text, 'max'::text]))),
    CONSTRAINT studio_humanization_runs_seo_target_check CHECK ((seo_target = 'linkedin'::text)),
    CONSTRAINT studio_humanization_runs_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'running'::text, 'succeeded'::text, 'failed'::text])))
);


--
-- Name: TABLE studio_humanization_runs; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.studio_humanization_runs IS 'Audit log of multi-pass humanizer runs (AI detector bypass + LinkedIn SEO)';


--
-- Name: studio_projects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.studio_projects (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    kind text NOT NULL,
    title text DEFAULT 'Untitled Project'::text NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    style_profile_id uuid,
    humanize_settings jsonb DEFAULT '{"enabled": false, "intensity": "standard", "auto_apply": false, "seo_target": null, "preserve_facts": true}'::jsonb NOT NULL,
    current_artifact_id uuid,
    thumbnail_path text,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    is_archived boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    last_opened_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT studio_projects_kind_check CHECK ((kind = ANY (ARRAY['pptx'::text, 'docx'::text, 'chat'::text, 'site'::text])))
);


--
-- Name: TABLE studio_projects; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.studio_projects IS 'Content Studio project — wraps a conversation with kind/style/humanize metadata';


--
-- Name: studio_writing_style_samples; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.studio_writing_style_samples (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    style_id uuid NOT NULL,
    user_id uuid NOT NULL,
    title text DEFAULT ''::text NOT NULL,
    source text DEFAULT 'paste'::text NOT NULL,
    source_url text,
    source_file_id text,
    text text NOT NULL,
    word_count integer DEFAULT 0 NOT NULL,
    char_count integer DEFAULT 0 NOT NULL,
    volume_path text,
    stats jsonb DEFAULT '{}'::jsonb NOT NULL,
    embedding public.vector(384),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT studio_writing_style_samples_source_check CHECK ((source = ANY (ARRAY['paste'::text, 'file'::text, 'url'::text])))
);


--
-- Name: TABLE studio_writing_style_samples; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.studio_writing_style_samples IS 'Raw writing samples used to clone a voice (text on volume + DB metadata)';


--
-- Name: studio_writing_styles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.studio_writing_styles (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    name text NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    icon text DEFAULT '✍️'::text NOT NULL,
    color text DEFAULT '#FEC00F'::text NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    voice_card jsonb,
    system_prompt text,
    exemplars jsonb DEFAULT '[]'::jsonb NOT NULL,
    embedding public.vector(384),
    fidelity_score double precision,
    sample_count integer DEFAULT 0 NOT NULL,
    total_words integer DEFAULT 0 NOT NULL,
    meta jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT studio_writing_styles_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'analyzing'::text, 'ready'::text, 'failed'::text])))
);


--
-- Name: TABLE studio_writing_styles; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.studio_writing_styles IS 'Per-user cloned voice profiles (1:1 voice cloning) for Content Studio';


--
-- Name: tool_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tool_results (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    conversation_id uuid,
    message_id uuid,
    tool_call_id text NOT NULL,
    tool_name text NOT NULL,
    input jsonb DEFAULT '{}'::jsonb NOT NULL,
    output jsonb,
    state text DEFAULT 'completed'::text NOT NULL,
    error_text text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT tool_results_state_check CHECK ((state = ANY (ARRAY['pending'::text, 'completed'::text, 'error'::text])))
);


--
-- Name: TABLE tool_results; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.tool_results IS 'One row per tool call executed during a chat turn. Stores the structured output (presentations, charts, research data) so the frontend can reconstruct Generative UI cards when revisiting a conversation without re-running the tool. message_id is backfilled by chat.py after the assistant message is saved.';


--
-- Name: usage_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.usage_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    event_type text NOT NULL,
    resource_type text,
    resource_id text,
    tokens_input integer DEFAULT 0,
    tokens_output integer DEFAULT 0,
    estimated_cost_cents integer DEFAULT 0,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: user_feedback; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_feedback (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    conversation_id uuid,
    message_id uuid,
    rating integer,
    feedback_type text,
    comment text,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT user_feedback_feedback_type_check CHECK ((feedback_type = ANY (ARRAY['rating'::text, 'bug'::text, 'feature'::text, 'general'::text]))),
    CONSTRAINT user_feedback_rating_check CHECK (((rating >= 1) AND (rating <= 5)))
);


--
-- Name: user_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_profiles (
    id uuid NOT NULL,
    email text NOT NULL,
    name text,
    nickname text,
    avatar_url text,
    is_admin boolean DEFAULT false,
    is_active boolean DEFAULT true,
    claude_api_key text,
    tavily_api_key text,
    preferences jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    last_active_at timestamp with time zone,
    claude_api_key_encrypted text,
    tavily_api_key_encrypted text,
    openai_api_key_encrypted text,
    openrouter_api_key_encrypted text,
    preferred_provider text DEFAULT 'anthropic'::text,
    preferred_model text DEFAULT 'claude-sonnet-4-20250514'::text,
    settings jsonb DEFAULT '{}'::jsonb,
    CONSTRAINT valid_email CHECK ((email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'::text))
);


--
-- Name: COLUMN user_profiles.openai_api_key_encrypted; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.user_profiles.openai_api_key_encrypted IS 'AES-256 encrypted OpenAI API key (user-provided)';


--
-- Name: COLUMN user_profiles.openrouter_api_key_encrypted; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.user_profiles.openrouter_api_key_encrypted IS 'AES-256 encrypted OpenRouter API key (user-provided)';


--
-- Name: COLUMN user_profiles.preferred_provider; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.user_profiles.preferred_provider IS 'User preferred LLM provider: anthropic, openai, openrouter, vercel_gateway';


--
-- Name: COLUMN user_profiles.preferred_model; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.user_profiles.preferred_model IS 'User preferred model ID (e.g. claude-sonnet-4-6, gpt-4o, meta-llama/llama-3.1-70b)';


--
-- Name: user_progress; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_progress (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    course_id uuid NOT NULL,
    completed_lessons text[] DEFAULT '{}'::text[] NOT NULL,
    progress_percent double precision DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: user_skill_audit; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_skill_audit (
    id bigint NOT NULL,
    slug text NOT NULL,
    actor_id uuid,
    action text NOT NULL,
    detail jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT user_skill_audit_action_check CHECK ((action = ANY (ARRAY['create'::text, 'update'::text, 'delete'::text, 'enable'::text, 'disable'::text, 'reconcile'::text, 'rehydrate'::text])))
);


--
-- Name: user_skill_audit_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_skill_audit_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_skill_audit_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_skill_audit_id_seq OWNED BY public.user_skill_audit.id;


--
-- Name: user_skills; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_skills (
    slug text NOT NULL,
    name text NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    category text DEFAULT 'general'::text NOT NULL,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    storage_kind text NOT NULL,
    storage_path text NOT NULL,
    bundle_size bigint DEFAULT 0 NOT NULL,
    file_count integer DEFAULT 0 NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    source text DEFAULT 'upload'::text NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT user_skills_source_check CHECK ((source = ANY (ARRAY['system'::text, 'upload'::text, 'inline'::text]))),
    CONSTRAINT user_skills_storage_kind_check CHECK ((storage_kind = ANY (ARRAY['lightweight'::text, 'bundle'::text])))
);


--
-- Name: user_yang_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_yang_settings (
    user_id uuid NOT NULL,
    subagents boolean DEFAULT true NOT NULL,
    parallel_tools boolean DEFAULT true NOT NULL,
    plan_mode boolean DEFAULT false NOT NULL,
    tool_search boolean DEFAULT true NOT NULL,
    auto_compact boolean DEFAULT true NOT NULL,
    focus_chain boolean DEFAULT true NOT NULL,
    background_edit boolean DEFAULT false NOT NULL,
    checkpoints boolean DEFAULT true NOT NULL,
    yolo_mode boolean DEFAULT false NOT NULL,
    double_check boolean DEFAULT false NOT NULL,
    advanced jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE user_yang_settings; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.user_yang_settings IS 'Per-user toggles for YANG advanced agentic features. Defaults tuned so the typical user gets safe behaviour out of the box.';


--
-- Name: workspace_files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workspace_files (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    conversation_id uuid NOT NULL,
    user_id uuid NOT NULL,
    filename text NOT NULL,
    language text DEFAULT 'python'::text NOT NULL,
    content text DEFAULT ''::text NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    last_author text DEFAULT 'agent'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE workspace_files; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.workspace_files IS 'Per-conversation code files surfaced in the IDE panel. One file per (conversation, filename). Agent and user both read/write.';


--
-- Name: yang_checkpoints; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.yang_checkpoints (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    conversation_id uuid NOT NULL,
    user_id uuid NOT NULL,
    label text,
    trigger text DEFAULT 'manual'::text NOT NULL,
    last_message_id uuid,
    focus_snapshot jsonb,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE yang_checkpoints; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.yang_checkpoints IS 'Rollback points. Restoring a checkpoint deletes messages newer than last_message_id and restores focus_snapshot. Generated files are NOT deleted — user is warned they persist on disk.';


--
-- Name: goal_steps id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.goal_steps ALTER COLUMN id SET DEFAULT nextval('public.goal_steps_id_seq'::regclass);


--
-- Name: memories id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memories ALTER COLUMN id SET DEFAULT nextval('public.memories_id_seq'::regclass);


--
-- Name: user_skill_audit id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_skill_audit ALTER COLUMN id SET DEFAULT nextval('public.user_skill_audit_id_seq'::regclass);


--
-- Name: afl_codes afl_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.afl_codes
    ADD CONSTRAINT afl_codes_pkey PRIMARY KEY (id);


--
-- Name: afl_feedback afl_feedback_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.afl_feedback
    ADD CONSTRAINT afl_feedback_pkey PRIMARY KEY (id);


--
-- Name: afl_history afl_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.afl_history
    ADD CONSTRAINT afl_history_pkey PRIMARY KEY (id);


--
-- Name: agent_inter_messages agent_inter_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_inter_messages
    ADD CONSTRAINT agent_inter_messages_pkey PRIMARY KEY (id);


--
-- Name: agent_messages agent_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_messages
    ADD CONSTRAINT agent_messages_pkey PRIMARY KEY (id);


--
-- Name: agent_team_members agent_team_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_team_members
    ADD CONSTRAINT agent_team_members_pkey PRIMARY KEY (id);


--
-- Name: agent_teams agent_teams_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_teams
    ADD CONSTRAINT agent_teams_pkey PRIMARY KEY (id);


--
-- Name: app_api_keys app_api_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.app_api_keys
    ADD CONSTRAINT app_api_keys_pkey PRIMARY KEY (id);


--
-- Name: attachments attachments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attachments
    ADD CONSTRAINT attachments_pkey PRIMARY KEY (id);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- Name: backtest_results backtest_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_results
    ADD CONSTRAINT backtest_results_pkey PRIMARY KEY (id);


--
-- Name: brain_chunks brain_chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.brain_chunks
    ADD CONSTRAINT brain_chunks_pkey PRIMARY KEY (id);


--
-- Name: brain_documents brain_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.brain_documents
    ADD CONSTRAINT brain_documents_pkey PRIMARY KEY (id);


--
-- Name: conversation_files conversation_files_conversation_id_file_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_files
    ADD CONSTRAINT conversation_files_conversation_id_file_id_key UNIQUE (conversation_id, file_id);


--
-- Name: conversation_files conversation_files_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_files
    ADD CONSTRAINT conversation_files_pkey PRIMARY KEY (id);


--
-- Name: conversation_focus conversation_focus_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_focus
    ADD CONSTRAINT conversation_focus_pkey PRIMARY KEY (conversation_id);


--
-- Name: conversations conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_pkey PRIMARY KEY (id);


--
-- Name: courses courses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.courses
    ADD CONSTRAINT courses_pkey PRIMARY KEY (id);


--
-- Name: file_chunks file_chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_chunks
    ADD CONSTRAINT file_chunks_pkey PRIMARY KEY (id);


--
-- Name: file_uploads file_uploads_bucket_id_storage_path_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_uploads
    ADD CONSTRAINT file_uploads_bucket_id_storage_path_key UNIQUE (bucket_id, storage_path);


--
-- Name: file_uploads file_uploads_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_uploads
    ADD CONSTRAINT file_uploads_pkey PRIMARY KEY (id);


--
-- Name: generated_files generated_files_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generated_files
    ADD CONSTRAINT generated_files_pkey PRIMARY KEY (file_id);


--
-- Name: goal_steps goal_steps_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.goal_steps
    ADD CONSTRAINT goal_steps_pkey PRIMARY KEY (id);


--
-- Name: goals goals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.goals
    ADD CONSTRAINT goals_pkey PRIMARY KEY (id);


--
-- Name: knowledge_stacks knowledge_stacks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_stacks
    ADD CONSTRAINT knowledge_stacks_pkey PRIMARY KEY (id);


--
-- Name: learnings learnings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.learnings
    ADD CONSTRAINT learnings_pkey PRIMARY KEY (id);


--
-- Name: memories memories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memories
    ADD CONSTRAINT memories_pkey PRIMARY KEY (id);


--
-- Name: memories memories_user_id_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memories
    ADD CONSTRAINT memories_user_id_key_key UNIQUE (user_id, key);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- Name: pptx_assets pptx_assets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pptx_assets
    ADD CONSTRAINT pptx_assets_pkey PRIMARY KEY (id);


--
-- Name: pptx_program_versions pptx_program_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pptx_program_versions
    ADD CONSTRAINT pptx_program_versions_pkey PRIMARY KEY (id);


--
-- Name: pptx_program_versions pptx_program_versions_program_id_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pptx_program_versions
    ADD CONSTRAINT pptx_program_versions_program_id_version_key UNIQUE (program_id, version);


--
-- Name: pptx_programs pptx_programs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pptx_programs
    ADD CONSTRAINT pptx_programs_pkey PRIMARY KEY (id);


--
-- Name: presentations presentations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.presentations
    ADD CONSTRAINT presentations_pkey PRIMARY KEY (id);


--
-- Name: published_sites published_sites_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.published_sites
    ADD CONSTRAINT published_sites_pkey PRIMARY KEY (id);


--
-- Name: quiz_results quiz_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quiz_results
    ADD CONSTRAINT quiz_results_pkey PRIMARY KEY (id);


--
-- Name: quizzes quizzes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quizzes
    ADD CONSTRAINT quizzes_pkey PRIMARY KEY (id);


--
-- Name: reverse_analyses reverse_analyses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reverse_analyses
    ADD CONSTRAINT reverse_analyses_pkey PRIMARY KEY (id);


--
-- Name: scheduled_jobs scheduled_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduled_jobs
    ADD CONSTRAINT scheduled_jobs_pkey PRIMARY KEY (id);


--
-- Name: studio_artifacts studio_artifacts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.studio_artifacts
    ADD CONSTRAINT studio_artifacts_pkey PRIMARY KEY (id);


--
-- Name: studio_humanization_runs studio_humanization_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.studio_humanization_runs
    ADD CONSTRAINT studio_humanization_runs_pkey PRIMARY KEY (id);


--
-- Name: studio_projects studio_projects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.studio_projects
    ADD CONSTRAINT studio_projects_pkey PRIMARY KEY (id);


--
-- Name: studio_writing_style_samples studio_writing_style_samples_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.studio_writing_style_samples
    ADD CONSTRAINT studio_writing_style_samples_pkey PRIMARY KEY (id);


--
-- Name: studio_writing_styles studio_writing_styles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.studio_writing_styles
    ADD CONSTRAINT studio_writing_styles_pkey PRIMARY KEY (id);


--
-- Name: tool_results tool_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tool_results
    ADD CONSTRAINT tool_results_pkey PRIMARY KEY (id);


--
-- Name: workspace_files uq_workspace_files_conv_filename; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_files
    ADD CONSTRAINT uq_workspace_files_conv_filename UNIQUE (conversation_id, filename);


--
-- Name: usage_events usage_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usage_events
    ADD CONSTRAINT usage_events_pkey PRIMARY KEY (id);


--
-- Name: user_feedback user_feedback_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_feedback
    ADD CONSTRAINT user_feedback_pkey PRIMARY KEY (id);


--
-- Name: user_profiles user_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_profiles
    ADD CONSTRAINT user_profiles_pkey PRIMARY KEY (id);


--
-- Name: user_progress user_progress_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_progress
    ADD CONSTRAINT user_progress_pkey PRIMARY KEY (id);


--
-- Name: user_progress user_progress_user_id_course_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_progress
    ADD CONSTRAINT user_progress_user_id_course_id_key UNIQUE (user_id, course_id);


--
-- Name: user_skill_audit user_skill_audit_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_skill_audit
    ADD CONSTRAINT user_skill_audit_pkey PRIMARY KEY (id);


--
-- Name: user_skills user_skills_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_skills
    ADD CONSTRAINT user_skills_pkey PRIMARY KEY (slug);


--
-- Name: user_yang_settings user_yang_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_yang_settings
    ADD CONSTRAINT user_yang_settings_pkey PRIMARY KEY (user_id);


--
-- Name: workspace_files workspace_files_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_files
    ADD CONSTRAINT workspace_files_pkey PRIMARY KEY (id);


--
-- Name: yang_checkpoints yang_checkpoints_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.yang_checkpoints
    ADD CONSTRAINT yang_checkpoints_pkey PRIMARY KEY (id);


--
-- Name: generated_files_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX generated_files_created_at_idx ON public.generated_files USING btree (created_at DESC);


--
-- Name: goal_steps_goal_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX goal_steps_goal_idx ON public.goal_steps USING btree (goal_id, idx);


--
-- Name: goal_steps_goal_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX goal_steps_goal_ts ON public.goal_steps USING btree (goal_id, ts);


--
-- Name: goals_user_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX goals_user_created_idx ON public.goals USING btree (user_id, created_at DESC);


--
-- Name: goals_user_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX goals_user_status_idx ON public.goals USING btree (user_id, status);


--
-- Name: idx_afl_codes_tags; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_afl_codes_tags ON public.afl_codes USING gin (tags);


--
-- Name: idx_afl_codes_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_afl_codes_user_id ON public.afl_codes USING btree (user_id);


--
-- Name: idx_afl_feedback_gen; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_afl_feedback_gen ON public.afl_feedback USING btree (generation_id);


--
-- Name: idx_afl_feedback_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_afl_feedback_user ON public.afl_feedback USING btree (user_id);


--
-- Name: idx_afl_history_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_afl_history_created_at ON public.afl_history USING btree (created_at DESC);


--
-- Name: idx_afl_history_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_afl_history_user_id ON public.afl_history USING btree (user_id);


--
-- Name: idx_agent_inter_messages_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_inter_messages_created_at ON public.agent_inter_messages USING btree (created_at);


--
-- Name: idx_agent_inter_messages_team_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_inter_messages_team_id ON public.agent_inter_messages USING btree (team_id);


--
-- Name: idx_agent_team_members_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_team_members_agent_id ON public.agent_team_members USING btree (agent_id);


--
-- Name: idx_app_api_keys_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_app_api_keys_user ON public.app_api_keys USING btree (user_id);


--
-- Name: idx_attachments_conv; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_attachments_conv ON public.attachments USING btree (conversation_id);


--
-- Name: idx_attachments_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_attachments_user ON public.attachments USING btree (user_id);


--
-- Name: idx_audit_logs_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_logs_action ON public.audit_logs USING btree (action, created_at DESC);


--
-- Name: idx_audit_logs_resource; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_logs_resource ON public.audit_logs USING btree (resource_type, resource_id);


--
-- Name: idx_audit_logs_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_logs_user_id ON public.audit_logs USING btree (user_id);


--
-- Name: idx_brain_chunks_chunk_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_brain_chunks_chunk_index ON public.brain_chunks USING btree (document_id, chunk_index);


--
-- Name: idx_brain_chunks_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_brain_chunks_document_id ON public.brain_chunks USING btree (document_id);


--
-- Name: idx_brain_chunks_embedding; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_brain_chunks_embedding ON public.brain_chunks USING ivfflat (embedding public.vector_cosine_ops) WITH (lists='100');


--
-- Name: idx_brain_documents_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_brain_documents_category ON public.brain_documents USING btree (category);


--
-- Name: idx_brain_documents_content_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_brain_documents_content_hash ON public.brain_documents USING btree (content_hash);


--
-- Name: idx_brain_documents_stack_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_brain_documents_stack_id ON public.brain_documents USING btree (stack_id);


--
-- Name: idx_brain_documents_uploaded_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_brain_documents_uploaded_by ON public.brain_documents USING btree (uploaded_by);


--
-- Name: idx_brain_documents_uploaded_by_stack; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_brain_documents_uploaded_by_stack ON public.brain_documents USING btree (uploaded_by, stack_id);


--
-- Name: idx_conversation_files_conversation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversation_files_conversation ON public.conversation_files USING btree (conversation_id);


--
-- Name: idx_conversation_focus_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversation_focus_user ON public.conversation_focus USING btree (user_id);


--
-- Name: idx_conversations_archived; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_archived ON public.conversations USING btree (user_id, is_archived) WHERE (is_archived = false);


--
-- Name: idx_conversations_updated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_updated_at ON public.conversations USING btree (updated_at DESC);


--
-- Name: idx_conversations_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_user_id ON public.conversations USING btree (user_id);


--
-- Name: idx_file_chunks_embedding; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_file_chunks_embedding ON public.file_chunks USING ivfflat (embedding public.vector_cosine_ops) WITH (lists='100');


--
-- Name: idx_file_chunks_file_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_file_chunks_file_id ON public.file_chunks USING btree (file_id);


--
-- Name: idx_file_uploads_content_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_file_uploads_content_hash ON public.file_uploads USING btree (content_hash);


--
-- Name: idx_file_uploads_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_file_uploads_status ON public.file_uploads USING btree (status);


--
-- Name: idx_file_uploads_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_file_uploads_user_id ON public.file_uploads USING btree (user_id);


--
-- Name: idx_generated_files_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_generated_files_created_at ON public.generated_files USING btree (created_at DESC);


--
-- Name: idx_generated_files_file_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_generated_files_file_id ON public.generated_files USING btree (file_id);


--
-- Name: idx_generated_files_tool_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_generated_files_tool_name ON public.generated_files USING btree (tool_name);


--
-- Name: idx_generated_files_tool_result; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_generated_files_tool_result ON public.generated_files USING btree (tool_result_id) WHERE (tool_result_id IS NOT NULL);


--
-- Name: idx_generated_files_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_generated_files_user_id ON public.generated_files USING btree (user_id);


--
-- Name: idx_humanization_runs_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_humanization_runs_project ON public.studio_humanization_runs USING btree (project_id, created_at DESC);


--
-- Name: idx_humanization_runs_style; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_humanization_runs_style ON public.studio_humanization_runs USING btree (style_profile_id);


--
-- Name: idx_humanization_runs_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_humanization_runs_user ON public.studio_humanization_runs USING btree (user_id, created_at DESC);


--
-- Name: idx_knowledge_stacks_updated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_knowledge_stacks_updated_at ON public.knowledge_stacks USING btree (updated_at DESC);


--
-- Name: idx_knowledge_stacks_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_knowledge_stacks_user_id ON public.knowledge_stacks USING btree (user_id);


--
-- Name: idx_knowledge_stacks_user_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_knowledge_stacks_user_name ON public.knowledge_stacks USING btree (user_id, name);


--
-- Name: idx_learnings_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_learnings_user_id ON public.learnings USING btree (user_id);


--
-- Name: idx_messages_conversation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_messages_conversation_id ON public.messages USING btree (conversation_id);


--
-- Name: idx_messages_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_messages_created_at ON public.messages USING btree (conversation_id, created_at);


--
-- Name: idx_messages_parts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_messages_parts ON public.messages USING gin (parts) WHERE (parts IS NOT NULL);


--
-- Name: idx_pptx_assets_owner; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pptx_assets_owner ON public.pptx_assets USING btree (owner_id) WHERE (owner_id IS NOT NULL);


--
-- Name: idx_pptx_assets_tags; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pptx_assets_tags ON public.pptx_assets USING gin (tags);


--
-- Name: idx_pptx_assets_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_pptx_assets_unique ON public.pptx_assets USING btree (scope, COALESCE(owner_id, '00000000-0000-0000-0000-000000000000'::uuid), key);


--
-- Name: idx_pptx_program_versions_program; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pptx_program_versions_program ON public.pptx_program_versions USING btree (program_id, version DESC);


--
-- Name: idx_pptx_programs_user_updated; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pptx_programs_user_updated ON public.pptx_programs USING btree (user_id, updated_at DESC);


--
-- Name: idx_presentations_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_presentations_created_at ON public.presentations USING btree (created_at DESC);


--
-- Name: idx_presentations_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_presentations_user_id ON public.presentations USING btree (user_id);


--
-- Name: idx_published_sites_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_published_sites_project_id ON public.published_sites USING btree (project_id);


--
-- Name: idx_published_sites_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_published_sites_user_id ON public.published_sites USING btree (user_id);


--
-- Name: idx_quiz_results_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_quiz_results_user ON public.quiz_results USING btree (user_id, quiz_id);


--
-- Name: idx_reverse_analyses_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_reverse_analyses_user ON public.reverse_analyses USING btree (user_id, created_at DESC);


--
-- Name: idx_studio_artifacts_conversation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_studio_artifacts_conversation_id ON public.studio_artifacts USING btree (conversation_id);


--
-- Name: idx_studio_artifacts_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_studio_artifacts_project_id ON public.studio_artifacts USING btree (project_id);


--
-- Name: idx_studio_artifacts_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_studio_artifacts_user_id ON public.studio_artifacts USING btree (user_id);


--
-- Name: idx_studio_projects_conversation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_studio_projects_conversation_id ON public.studio_projects USING btree (conversation_id);


--
-- Name: idx_studio_projects_updated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_studio_projects_updated_at ON public.studio_projects USING btree (updated_at DESC);


--
-- Name: idx_studio_projects_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_studio_projects_user_id ON public.studio_projects USING btree (user_id);


--
-- Name: idx_studio_projects_user_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_studio_projects_user_kind ON public.studio_projects USING btree (user_id, kind) WHERE (NOT is_archived);


--
-- Name: idx_studio_writing_style_samples_style; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_studio_writing_style_samples_style ON public.studio_writing_style_samples USING btree (style_id);


--
-- Name: idx_studio_writing_style_samples_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_studio_writing_style_samples_user ON public.studio_writing_style_samples USING btree (user_id);


--
-- Name: idx_studio_writing_styles_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_studio_writing_styles_status ON public.studio_writing_styles USING btree (status);


--
-- Name: idx_studio_writing_styles_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_studio_writing_styles_user ON public.studio_writing_styles USING btree (user_id);


--
-- Name: idx_tool_results_call_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tool_results_call_id ON public.tool_results USING btree (tool_call_id);


--
-- Name: idx_tool_results_conv; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tool_results_conv ON public.tool_results USING btree (conversation_id);


--
-- Name: idx_tool_results_conversation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tool_results_conversation ON public.tool_results USING btree (conversation_id);


--
-- Name: idx_tool_results_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tool_results_created_at ON public.tool_results USING btree (created_at DESC);


--
-- Name: idx_tool_results_message; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tool_results_message ON public.tool_results USING btree (message_id);


--
-- Name: idx_tool_results_msg; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tool_results_msg ON public.tool_results USING btree (message_id);


--
-- Name: idx_tool_results_tool_call; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tool_results_tool_call ON public.tool_results USING btree (tool_call_id);


--
-- Name: idx_tool_results_tool_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tool_results_tool_name ON public.tool_results USING btree (tool_name);


--
-- Name: idx_tool_results_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tool_results_user ON public.tool_results USING btree (user_id);


--
-- Name: idx_usage_events_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_usage_events_created_at ON public.usage_events USING btree (created_at DESC);


--
-- Name: idx_usage_events_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_usage_events_type ON public.usage_events USING btree (event_type, created_at DESC);


--
-- Name: idx_usage_events_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_usage_events_user_id ON public.usage_events USING btree (user_id);


--
-- Name: idx_user_feedback_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_feedback_created_at ON public.user_feedback USING btree (created_at DESC);


--
-- Name: idx_user_feedback_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_feedback_user_id ON public.user_feedback USING btree (user_id);


--
-- Name: idx_user_profiles_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_profiles_created_at ON public.user_profiles USING btree (created_at DESC);


--
-- Name: idx_user_profiles_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_profiles_email ON public.user_profiles USING btree (email);


--
-- Name: idx_user_profiles_last_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_profiles_last_active ON public.user_profiles USING btree (last_active_at DESC);


--
-- Name: idx_user_progress_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_progress_user ON public.user_progress USING btree (user_id);


--
-- Name: idx_user_skill_audit_actor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_skill_audit_actor ON public.user_skill_audit USING btree (actor_id);


--
-- Name: idx_user_skill_audit_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_skill_audit_created_at ON public.user_skill_audit USING btree (created_at DESC);


--
-- Name: idx_user_skill_audit_slug; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_skill_audit_slug ON public.user_skill_audit USING btree (slug);


--
-- Name: idx_user_skills_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_skills_category ON public.user_skills USING btree (category);


--
-- Name: idx_user_skills_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_skills_created_by ON public.user_skills USING btree (created_by);


--
-- Name: idx_user_skills_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_skills_enabled ON public.user_skills USING btree (enabled);


--
-- Name: idx_user_skills_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_skills_source ON public.user_skills USING btree (source);


--
-- Name: idx_workspace_files_conversation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workspace_files_conversation ON public.workspace_files USING btree (conversation_id, updated_at DESC);


--
-- Name: idx_workspace_files_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workspace_files_user ON public.workspace_files USING btree (user_id);


--
-- Name: idx_yang_checkpoints_conversation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_yang_checkpoints_conversation ON public.yang_checkpoints USING btree (conversation_id);


--
-- Name: idx_yang_checkpoints_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_yang_checkpoints_created ON public.yang_checkpoints USING btree (created_at DESC);


--
-- Name: idx_yang_checkpoints_trigger; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_yang_checkpoints_trigger ON public.yang_checkpoints USING btree (trigger);


--
-- Name: idx_yang_checkpoints_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_yang_checkpoints_user ON public.yang_checkpoints USING btree (user_id);


--
-- Name: memories_embedding_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX memories_embedding_idx ON public.memories USING ivfflat (embedding public.vector_cosine_ops) WITH (lists='100');


--
-- Name: memories_user_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX memories_user_idx ON public.memories USING btree (user_id);


--
-- Name: memories_user_updated_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX memories_user_updated_idx ON public.memories USING btree (user_id, updated_at DESC);


--
-- Name: scheduled_jobs_due_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX scheduled_jobs_due_idx ON public.scheduled_jobs USING btree (next_run_at) WHERE (enabled = true);


--
-- Name: scheduled_jobs_user_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX scheduled_jobs_user_idx ON public.scheduled_jobs USING btree (user_id);


--
-- Name: uq_published_sites_custom_domain_active; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_published_sites_custom_domain_active ON public.published_sites USING btree (lower(custom_domain)) WHERE (is_active AND (custom_domain IS NOT NULL));


--
-- Name: uq_published_sites_subdomain_active; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_published_sites_subdomain_active ON public.published_sites USING btree (lower(subdomain)) WHERE is_active;


--
-- Name: uq_studio_artifacts_project_version; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_studio_artifacts_project_version ON public.studio_artifacts USING btree (project_id, version);


--
-- Name: uq_studio_writing_styles_user_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_studio_writing_styles_user_name ON public.studio_writing_styles USING btree (user_id, name);


--
-- Name: uq_tool_results_call_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_tool_results_call_id ON public.tool_results USING btree (tool_call_id);


--
-- Name: user_profiles audit_user_profiles; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER audit_user_profiles AFTER INSERT OR DELETE OR UPDATE ON public.user_profiles FOR EACH ROW EXECUTE FUNCTION public.audit_log_trigger();


--
-- Name: brain_documents brain_documents_stack_stats; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER brain_documents_stack_stats AFTER INSERT OR DELETE OR UPDATE ON public.brain_documents FOR EACH ROW EXECUTE FUNCTION public.trg_brain_documents_stack_stats();


--
-- Name: knowledge_stacks knowledge_stacks_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER knowledge_stacks_updated_at BEFORE UPDATE ON public.knowledge_stacks FOR EACH ROW EXECUTE FUNCTION public.trg_knowledge_stacks_updated_at();


--
-- Name: pptx_assets pptx_assets_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER pptx_assets_touch BEFORE UPDATE ON public.pptx_assets FOR EACH ROW EXECUTE FUNCTION public._pptx_assets_touch();


--
-- Name: pptx_programs pptx_programs_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER pptx_programs_touch BEFORE UPDATE ON public.pptx_programs FOR EACH ROW EXECUTE FUNCTION public._pptx_programs_touch();


--
-- Name: published_sites published_sites_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER published_sites_updated_at BEFORE UPDATE ON public.published_sites FOR EACH ROW EXECUTE FUNCTION public.trg_published_sites_updated_at();


--
-- Name: studio_artifacts studio_artifacts_touch_project; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER studio_artifacts_touch_project AFTER INSERT OR UPDATE ON public.studio_artifacts FOR EACH ROW EXECUTE FUNCTION public.trg_studio_artifacts_touch_project();


--
-- Name: studio_projects studio_projects_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER studio_projects_updated_at BEFORE UPDATE ON public.studio_projects FOR EACH ROW EXECUTE FUNCTION public.trg_studio_projects_updated_at();


--
-- Name: studio_writing_style_samples studio_writing_style_samples_stats; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER studio_writing_style_samples_stats AFTER INSERT OR DELETE OR UPDATE ON public.studio_writing_style_samples FOR EACH ROW EXECUTE FUNCTION public.trg_studio_writing_style_samples_stats();


--
-- Name: studio_writing_styles studio_writing_styles_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER studio_writing_styles_updated_at BEFORE UPDATE ON public.studio_writing_styles FOR EACH ROW EXECUTE FUNCTION public.trg_studio_writing_styles_updated_at();


--
-- Name: conversation_focus trg_conversation_focus_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_conversation_focus_updated_at BEFORE UPDATE ON public.conversation_focus FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: goals trg_goals_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_goals_updated_at BEFORE UPDATE ON public.goals FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: memories trg_memories_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_memories_updated_at BEFORE UPDATE ON public.memories FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: scheduled_jobs trg_scheduled_jobs_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_scheduled_jobs_updated_at BEFORE UPDATE ON public.scheduled_jobs FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: user_skills trg_user_skills_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_user_skills_updated_at BEFORE UPDATE ON public.user_skills FOR EACH ROW EXECUTE FUNCTION public.user_skills_set_updated_at();


--
-- Name: user_yang_settings trg_user_yang_settings_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_user_yang_settings_updated_at BEFORE UPDATE ON public.user_yang_settings FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: workspace_files trg_workspace_files_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_workspace_files_touch BEFORE UPDATE ON public.workspace_files FOR EACH ROW EXECUTE FUNCTION public.workspace_files_touch_updated_at();


--
-- Name: afl_codes update_afl_codes_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_afl_codes_updated_at BEFORE UPDATE ON public.afl_codes FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: conversations update_conversations_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_conversations_updated_at BEFORE UPDATE ON public.conversations FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: tool_results update_tool_results_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_tool_results_updated_at BEFORE UPDATE ON public.tool_results FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: user_profiles update_user_profiles_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_user_profiles_updated_at BEFORE UPDATE ON public.user_profiles FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: afl_codes afl_codes_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.afl_codes
    ADD CONSTRAINT afl_codes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_profiles(id) ON DELETE CASCADE;


--
-- Name: afl_feedback afl_feedback_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.afl_feedback
    ADD CONSTRAINT afl_feedback_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: afl_history afl_history_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.afl_history
    ADD CONSTRAINT afl_history_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_profiles(id) ON DELETE CASCADE;


--
-- Name: agent_inter_messages agent_inter_messages_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_inter_messages
    ADD CONSTRAINT agent_inter_messages_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.agent_teams(id) ON DELETE CASCADE;


--
-- Name: agent_messages agent_messages_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_messages
    ADD CONSTRAINT agent_messages_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.agent_teams(id) ON DELETE CASCADE;


--
-- Name: agent_team_members agent_team_members_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_team_members
    ADD CONSTRAINT agent_team_members_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.agent_teams(id) ON DELETE CASCADE;


--
-- Name: agent_teams agent_teams_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_teams
    ADD CONSTRAINT agent_teams_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: app_api_keys app_api_keys_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.app_api_keys
    ADD CONSTRAINT app_api_keys_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: attachments attachments_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attachments
    ADD CONSTRAINT attachments_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: attachments attachments_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attachments
    ADD CONSTRAINT attachments_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: audit_logs audit_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE SET NULL;


--
-- Name: backtest_results backtest_results_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_results
    ADD CONSTRAINT backtest_results_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_profiles(id);


--
-- Name: brain_chunks brain_chunks_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.brain_chunks
    ADD CONSTRAINT brain_chunks_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.brain_documents(id) ON DELETE CASCADE;


--
-- Name: brain_documents brain_documents_stack_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.brain_documents
    ADD CONSTRAINT brain_documents_stack_id_fkey FOREIGN KEY (stack_id) REFERENCES public.knowledge_stacks(id) ON DELETE SET NULL;


--
-- Name: conversation_files conversation_files_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_files
    ADD CONSTRAINT conversation_files_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: conversation_files conversation_files_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_files
    ADD CONSTRAINT conversation_files_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.file_uploads(id) ON DELETE CASCADE;


--
-- Name: conversation_focus conversation_focus_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_focus
    ADD CONSTRAINT conversation_focus_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: conversations conversations_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_profiles(id) ON DELETE CASCADE;


--
-- Name: file_chunks file_chunks_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_chunks
    ADD CONSTRAINT file_chunks_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.file_uploads(id) ON DELETE CASCADE;


--
-- Name: file_uploads file_uploads_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_uploads
    ADD CONSTRAINT file_uploads_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_profiles(id) ON DELETE CASCADE;


--
-- Name: workspace_files fk_workspace_files_conversation; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_files
    ADD CONSTRAINT fk_workspace_files_conversation FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: workspace_files fk_workspace_files_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_files
    ADD CONSTRAINT fk_workspace_files_user FOREIGN KEY (user_id) REFERENCES public.user_profiles(id) ON DELETE CASCADE;


--
-- Name: generated_files generated_files_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generated_files
    ADD CONSTRAINT generated_files_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_profiles(id) ON DELETE SET NULL;


--
-- Name: goal_steps goal_steps_goal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.goal_steps
    ADD CONSTRAINT goal_steps_goal_id_fkey FOREIGN KEY (goal_id) REFERENCES public.goals(id) ON DELETE CASCADE;


--
-- Name: goals goals_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.goals
    ADD CONSTRAINT goals_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: learnings learnings_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.learnings
    ADD CONSTRAINT learnings_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.brain_documents(id) ON DELETE CASCADE;


--
-- Name: memories memories_source_goal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memories
    ADD CONSTRAINT memories_source_goal_id_fkey FOREIGN KEY (source_goal_id) REFERENCES public.goals(id) ON DELETE SET NULL;


--
-- Name: memories memories_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memories
    ADD CONSTRAINT memories_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: messages messages_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: pptx_program_versions pptx_program_versions_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pptx_program_versions
    ADD CONSTRAINT pptx_program_versions_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.pptx_programs(id) ON DELETE CASCADE;


--
-- Name: pptx_programs pptx_programs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pptx_programs
    ADD CONSTRAINT pptx_programs_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: presentations presentations_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.presentations
    ADD CONSTRAINT presentations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_profiles(id) ON DELETE CASCADE;


--
-- Name: published_sites published_sites_artifact_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.published_sites
    ADD CONSTRAINT published_sites_artifact_id_fkey FOREIGN KEY (artifact_id) REFERENCES public.studio_artifacts(id) ON DELETE CASCADE;


--
-- Name: published_sites published_sites_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.published_sites
    ADD CONSTRAINT published_sites_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.studio_projects(id) ON DELETE CASCADE;


--
-- Name: published_sites published_sites_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.published_sites
    ADD CONSTRAINT published_sites_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: quiz_results quiz_results_quiz_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quiz_results
    ADD CONSTRAINT quiz_results_quiz_id_fkey FOREIGN KEY (quiz_id) REFERENCES public.quizzes(id) ON DELETE CASCADE;


--
-- Name: quiz_results quiz_results_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quiz_results
    ADD CONSTRAINT quiz_results_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: quizzes quizzes_course_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quizzes
    ADD CONSTRAINT quizzes_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;


--
-- Name: reverse_analyses reverse_analyses_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reverse_analyses
    ADD CONSTRAINT reverse_analyses_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: scheduled_jobs scheduled_jobs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduled_jobs
    ADD CONSTRAINT scheduled_jobs_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: studio_artifacts studio_artifacts_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.studio_artifacts
    ADD CONSTRAINT studio_artifacts_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE SET NULL;


--
-- Name: studio_artifacts studio_artifacts_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.studio_artifacts
    ADD CONSTRAINT studio_artifacts_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.studio_projects(id) ON DELETE CASCADE;


--
-- Name: studio_artifacts studio_artifacts_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.studio_artifacts
    ADD CONSTRAINT studio_artifacts_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: studio_humanization_runs studio_humanization_runs_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.studio_humanization_runs
    ADD CONSTRAINT studio_humanization_runs_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE SET NULL;


--
-- Name: studio_humanization_runs studio_humanization_runs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.studio_humanization_runs
    ADD CONSTRAINT studio_humanization_runs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.studio_projects(id) ON DELETE SET NULL;


--
-- Name: studio_humanization_runs studio_humanization_runs_style_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.studio_humanization_runs
    ADD CONSTRAINT studio_humanization_runs_style_profile_id_fkey FOREIGN KEY (style_profile_id) REFERENCES public.studio_writing_styles(id) ON DELETE SET NULL;


--
-- Name: studio_humanization_runs studio_humanization_runs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.studio_humanization_runs
    ADD CONSTRAINT studio_humanization_runs_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: studio_projects studio_projects_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.studio_projects
    ADD CONSTRAINT studio_projects_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: studio_projects studio_projects_current_artifact_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.studio_projects
    ADD CONSTRAINT studio_projects_current_artifact_fk FOREIGN KEY (current_artifact_id) REFERENCES public.studio_artifacts(id) ON DELETE SET NULL;


--
-- Name: studio_projects studio_projects_style_profile_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.studio_projects
    ADD CONSTRAINT studio_projects_style_profile_fk FOREIGN KEY (style_profile_id) REFERENCES public.studio_writing_styles(id) ON DELETE SET NULL;


--
-- Name: studio_projects studio_projects_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.studio_projects
    ADD CONSTRAINT studio_projects_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: studio_writing_style_samples studio_writing_style_samples_style_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.studio_writing_style_samples
    ADD CONSTRAINT studio_writing_style_samples_style_id_fkey FOREIGN KEY (style_id) REFERENCES public.studio_writing_styles(id) ON DELETE CASCADE;


--
-- Name: studio_writing_style_samples studio_writing_style_samples_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.studio_writing_style_samples
    ADD CONSTRAINT studio_writing_style_samples_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: studio_writing_styles studio_writing_styles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.studio_writing_styles
    ADD CONSTRAINT studio_writing_styles_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: tool_results tool_results_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tool_results
    ADD CONSTRAINT tool_results_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: tool_results tool_results_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tool_results
    ADD CONSTRAINT tool_results_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_profiles(id) ON DELETE CASCADE;


--
-- Name: usage_events usage_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usage_events
    ADD CONSTRAINT usage_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_profiles(id) ON DELETE SET NULL;


--
-- Name: user_feedback user_feedback_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_feedback
    ADD CONSTRAINT user_feedback_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE SET NULL;


--
-- Name: user_feedback user_feedback_message_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_feedback
    ADD CONSTRAINT user_feedback_message_id_fkey FOREIGN KEY (message_id) REFERENCES public.messages(id) ON DELETE SET NULL;


--
-- Name: user_feedback user_feedback_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_feedback
    ADD CONSTRAINT user_feedback_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_profiles(id) ON DELETE SET NULL;


--
-- Name: user_profiles user_profiles_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_profiles
    ADD CONSTRAINT user_profiles_id_fkey FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: user_progress user_progress_course_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_progress
    ADD CONSTRAINT user_progress_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;


--
-- Name: user_progress user_progress_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_progress
    ADD CONSTRAINT user_progress_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: user_skill_audit user_skill_audit_actor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_skill_audit
    ADD CONSTRAINT user_skill_audit_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES auth.users(id) ON DELETE SET NULL;


--
-- Name: user_skills user_skills_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_skills
    ADD CONSTRAINT user_skills_created_by_fkey FOREIGN KEY (created_by) REFERENCES auth.users(id) ON DELETE SET NULL;


--
-- Name: user_yang_settings user_yang_settings_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_yang_settings
    ADD CONSTRAINT user_yang_settings_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: yang_checkpoints yang_checkpoints_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.yang_checkpoints
    ADD CONSTRAINT yang_checkpoints_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: audit_logs Admins can read audit logs; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Admins can read audit logs" ON public.audit_logs FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1
   FROM public.user_profiles
  WHERE ((user_profiles.id = auth.uid()) AND (user_profiles.is_admin = true)))));


--
-- Name: courses Anyone reads courses; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Anyone reads courses" ON public.courses FOR SELECT USING (true);


--
-- Name: quizzes Anyone reads quizzes; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Anyone reads quizzes" ON public.quizzes FOR SELECT USING (true);


--
-- Name: conversation_files Users can access files in own conversations; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can access files in own conversations" ON public.conversation_files TO authenticated USING ((conversation_id IN ( SELECT conversations.id
   FROM public.conversations
  WHERE (conversations.user_id = auth.uid()))));


--
-- Name: backtest_results Users can delete own backtest results; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can delete own backtest results" ON public.backtest_results FOR DELETE USING ((auth.uid() = user_id));


--
-- Name: backtest_results Users can insert backtest results; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can insert backtest results" ON public.backtest_results FOR INSERT WITH CHECK ((auth.uid() = user_id));


--
-- Name: usage_events Users can insert usage events; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can insert usage events" ON public.usage_events FOR INSERT TO authenticated WITH CHECK ((user_id = auth.uid()));


--
-- Name: messages Users can manage messages in own conversations; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can manage messages in own conversations" ON public.messages TO authenticated USING ((conversation_id IN ( SELECT conversations.id
   FROM public.conversations
  WHERE (conversations.user_id = auth.uid())))) WITH CHECK ((conversation_id IN ( SELECT conversations.id
   FROM public.conversations
  WHERE (conversations.user_id = auth.uid()))));


--
-- Name: afl_codes Users can manage own AFL codes; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can manage own AFL codes" ON public.afl_codes TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));


--
-- Name: afl_history Users can manage own AFL history; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can manage own AFL history" ON public.afl_history TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));


--
-- Name: conversations Users can manage own conversations; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can manage own conversations" ON public.conversations TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));


--
-- Name: user_feedback Users can manage own feedback; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can manage own feedback" ON public.user_feedback TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));


--
-- Name: file_uploads Users can manage own file uploads; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can manage own file uploads" ON public.file_uploads TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));


--
-- Name: presentations Users can manage own presentations; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can manage own presentations" ON public.presentations TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));


--
-- Name: backtest_results Users can read own backtest results; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can read own backtest results" ON public.backtest_results USING ((auth.uid() = user_id));


--
-- Name: user_profiles Users can read own profile; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can read own profile" ON public.user_profiles FOR SELECT TO authenticated USING ((auth.uid() = id));


--
-- Name: usage_events Users can read own usage events; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can read own usage events" ON public.usage_events FOR SELECT TO authenticated USING ((auth.uid() = user_id));


--
-- Name: backtest_results Users can update own backtest results; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can update own backtest results" ON public.backtest_results FOR UPDATE USING ((auth.uid() = user_id));


--
-- Name: user_profiles Users can update own profile; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can update own profile" ON public.user_profiles FOR UPDATE TO authenticated USING ((auth.uid() = id)) WITH CHECK ((auth.uid() = id));


--
-- Name: tool_results Users insert own tool_results; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users insert own tool_results" ON public.tool_results FOR INSERT WITH CHECK ((auth.uid() = user_id));


--
-- Name: afl_feedback Users own afl_feedback; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users own afl_feedback" ON public.afl_feedback USING ((auth.uid() = user_id));


--
-- Name: app_api_keys Users own app_api_keys; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users own app_api_keys" ON public.app_api_keys USING ((auth.uid() = user_id));


--
-- Name: attachments Users own attachments; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users own attachments" ON public.attachments USING ((auth.uid() = user_id));


--
-- Name: quiz_results Users own quiz_results; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users own quiz_results" ON public.quiz_results USING ((auth.uid() = user_id));


--
-- Name: reverse_analyses Users own reverse_analyses; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users own reverse_analyses" ON public.reverse_analyses USING ((auth.uid() = user_id));


--
-- Name: user_progress Users own user_progress; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users own user_progress" ON public.user_progress USING ((auth.uid() = user_id));


--
-- Name: tool_results Users update own tool_results; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users update own tool_results" ON public.tool_results FOR UPDATE USING ((auth.uid() = user_id));


--
-- Name: tool_results Users view own tool_results; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users view own tool_results" ON public.tool_results FOR SELECT USING ((auth.uid() = user_id));


--
-- Name: afl_codes; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.afl_codes ENABLE ROW LEVEL SECURITY;

--
-- Name: afl_feedback; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.afl_feedback ENABLE ROW LEVEL SECURITY;

--
-- Name: afl_history; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.afl_history ENABLE ROW LEVEL SECURITY;

--
-- Name: app_api_keys; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.app_api_keys ENABLE ROW LEVEL SECURITY;

--
-- Name: attachments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.attachments ENABLE ROW LEVEL SECURITY;

--
-- Name: audit_logs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

--
-- Name: generated_files backend_insert_generated_files; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY backend_insert_generated_files ON public.generated_files FOR INSERT TO authenticated, anon, service_role WITH CHECK (true);


--
-- Name: generated_files backend_read_generated_files; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY backend_read_generated_files ON public.generated_files FOR SELECT TO authenticated, anon, service_role USING (true);


--
-- Name: generated_files backend_update_generated_files; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY backend_update_generated_files ON public.generated_files FOR UPDATE TO authenticated, anon, service_role USING (true);


--
-- Name: backtest_results; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.backtest_results ENABLE ROW LEVEL SECURITY;

--
-- Name: brain_chunks; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.brain_chunks ENABLE ROW LEVEL SECURITY;

--
-- Name: brain_chunks brain_chunks_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY brain_chunks_all ON public.brain_chunks USING (true) WITH CHECK (true);


--
-- Name: brain_documents; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.brain_documents ENABLE ROW LEVEL SECURITY;

--
-- Name: brain_documents brain_documents_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY brain_documents_all ON public.brain_documents USING (true) WITH CHECK (true);


--
-- Name: yang_checkpoints ckpt_owner; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY ckpt_owner ON public.yang_checkpoints TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));


--
-- Name: yang_checkpoints ckpt_service_role; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY ckpt_service_role ON public.yang_checkpoints TO service_role USING (true) WITH CHECK (true);


--
-- Name: conversation_files; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.conversation_files ENABLE ROW LEVEL SECURITY;

--
-- Name: conversation_focus; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.conversation_focus ENABLE ROW LEVEL SECURITY;

--
-- Name: conversations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;

--
-- Name: courses; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.courses ENABLE ROW LEVEL SECURITY;

--
-- Name: file_chunks; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.file_chunks ENABLE ROW LEVEL SECURITY;

--
-- Name: file_chunks file_chunks_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY file_chunks_all ON public.file_chunks USING (true) WITH CHECK (true);


--
-- Name: file_uploads; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.file_uploads ENABLE ROW LEVEL SECURITY;

--
-- Name: conversation_focus focus_owner; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY focus_owner ON public.conversation_focus TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));


--
-- Name: conversation_focus focus_service_role; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY focus_service_role ON public.conversation_focus TO service_role USING (true) WITH CHECK (true);


--
-- Name: generated_files; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.generated_files ENABLE ROW LEVEL SECURITY;

--
-- Name: generated_files generated_files_service_role_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY generated_files_service_role_all ON public.generated_files TO service_role USING (true) WITH CHECK (true);


--
-- Name: generated_files generated_files_user_insert; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY generated_files_user_insert ON public.generated_files FOR INSERT TO authenticated WITH CHECK (((user_id IS NULL) OR (user_id = auth.uid())));


--
-- Name: generated_files generated_files_user_select; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY generated_files_user_select ON public.generated_files FOR SELECT TO authenticated USING (((user_id IS NULL) OR (user_id = auth.uid())));


--
-- Name: generated_files generated_files_user_update; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY generated_files_user_update ON public.generated_files FOR UPDATE TO authenticated USING (((user_id IS NULL) OR (user_id = auth.uid()))) WITH CHECK (((user_id IS NULL) OR (user_id = auth.uid())));


--
-- Name: goal_steps; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.goal_steps ENABLE ROW LEVEL SECURITY;

--
-- Name: goal_steps goal_steps_owner; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY goal_steps_owner ON public.goal_steps TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));


--
-- Name: goal_steps goal_steps_service_role; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY goal_steps_service_role ON public.goal_steps TO service_role USING (true) WITH CHECK (true);


--
-- Name: goals; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.goals ENABLE ROW LEVEL SECURITY;

--
-- Name: goals goals_owner; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY goals_owner ON public.goals TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));


--
-- Name: goals goals_service_role; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY goals_service_role ON public.goals TO service_role USING (true) WITH CHECK (true);


--
-- Name: learnings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.learnings ENABLE ROW LEVEL SECURITY;

--
-- Name: learnings learnings_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY learnings_all ON public.learnings USING (true) WITH CHECK (true);


--
-- Name: memories; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.memories ENABLE ROW LEVEL SECURITY;

--
-- Name: memories memories_owner; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY memories_owner ON public.memories TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));


--
-- Name: memories memories_service_role; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY memories_service_role ON public.memories TO service_role USING (true) WITH CHECK (true);


--
-- Name: messages; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;

--
-- Name: pptx_assets; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pptx_assets ENABLE ROW LEVEL SECURITY;

--
-- Name: pptx_assets pptx_assets_delete_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY pptx_assets_delete_own ON public.pptx_assets FOR DELETE USING (((scope = 'user'::public.pptx_asset_scope) AND (owner_id = auth.uid())));


--
-- Name: pptx_assets pptx_assets_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY pptx_assets_read ON public.pptx_assets FOR SELECT USING (((scope = 'global'::public.pptx_asset_scope) OR ((scope = 'user'::public.pptx_asset_scope) AND (owner_id = auth.uid()))));


--
-- Name: pptx_assets pptx_assets_update_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY pptx_assets_update_own ON public.pptx_assets FOR UPDATE USING (((scope = 'user'::public.pptx_asset_scope) AND (owner_id = auth.uid()))) WITH CHECK (((scope = 'user'::public.pptx_asset_scope) AND (owner_id = auth.uid())));


--
-- Name: pptx_assets pptx_assets_write_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY pptx_assets_write_own ON public.pptx_assets FOR INSERT WITH CHECK (((scope = 'user'::public.pptx_asset_scope) AND (owner_id = auth.uid())));


--
-- Name: pptx_program_versions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pptx_program_versions ENABLE ROW LEVEL SECURITY;

--
-- Name: pptx_program_versions pptx_program_versions_self; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY pptx_program_versions_self ON public.pptx_program_versions USING ((EXISTS ( SELECT 1
   FROM public.pptx_programs p
  WHERE ((p.id = pptx_program_versions.program_id) AND (p.user_id = auth.uid()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM public.pptx_programs p
  WHERE ((p.id = pptx_program_versions.program_id) AND (p.user_id = auth.uid())))));


--
-- Name: pptx_programs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pptx_programs ENABLE ROW LEVEL SECURITY;

--
-- Name: pptx_programs pptx_programs_self; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY pptx_programs_self ON public.pptx_programs USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));


--
-- Name: presentations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.presentations ENABLE ROW LEVEL SECURITY;

--
-- Name: published_sites; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.published_sites ENABLE ROW LEVEL SECURITY;

--
-- Name: published_sites published_sites_owner_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY published_sites_owner_all ON public.published_sites USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));


--
-- Name: published_sites published_sites_public_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY published_sites_public_read ON public.published_sites FOR SELECT USING (is_active);


--
-- Name: published_sites published_sites_service; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY published_sites_service ON public.published_sites USING ((auth.role() = 'service_role'::text)) WITH CHECK ((auth.role() = 'service_role'::text));


--
-- Name: quiz_results; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.quiz_results ENABLE ROW LEVEL SECURITY;

--
-- Name: quizzes; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.quizzes ENABLE ROW LEVEL SECURITY;

--
-- Name: reverse_analyses; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.reverse_analyses ENABLE ROW LEVEL SECURITY;

--
-- Name: scheduled_jobs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.scheduled_jobs ENABLE ROW LEVEL SECURITY;

--
-- Name: scheduled_jobs scheduled_jobs_owner; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY scheduled_jobs_owner ON public.scheduled_jobs TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));


--
-- Name: scheduled_jobs scheduled_jobs_service_role; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY scheduled_jobs_service_role ON public.scheduled_jobs TO service_role USING (true) WITH CHECK (true);


--
-- Name: generated_files service_role_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY service_role_all ON public.generated_files TO service_role USING (true) WITH CHECK (true);


--
-- Name: studio_artifacts; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.studio_artifacts ENABLE ROW LEVEL SECURITY;

--
-- Name: studio_artifacts studio_artifacts_owner_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY studio_artifacts_owner_all ON public.studio_artifacts USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));


--
-- Name: studio_artifacts studio_artifacts_service; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY studio_artifacts_service ON public.studio_artifacts USING ((auth.role() = 'service_role'::text)) WITH CHECK ((auth.role() = 'service_role'::text));


--
-- Name: studio_humanization_runs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.studio_humanization_runs ENABLE ROW LEVEL SECURITY;

--
-- Name: studio_humanization_runs studio_humanization_runs_owner_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY studio_humanization_runs_owner_all ON public.studio_humanization_runs USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));


--
-- Name: studio_humanization_runs studio_humanization_runs_service; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY studio_humanization_runs_service ON public.studio_humanization_runs USING ((auth.role() = 'service_role'::text)) WITH CHECK ((auth.role() = 'service_role'::text));


--
-- Name: studio_projects; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.studio_projects ENABLE ROW LEVEL SECURITY;

--
-- Name: studio_projects studio_projects_owner_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY studio_projects_owner_all ON public.studio_projects USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));


--
-- Name: studio_projects studio_projects_service; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY studio_projects_service ON public.studio_projects USING ((auth.role() = 'service_role'::text)) WITH CHECK ((auth.role() = 'service_role'::text));


--
-- Name: studio_writing_style_samples; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.studio_writing_style_samples ENABLE ROW LEVEL SECURITY;

--
-- Name: studio_writing_style_samples studio_writing_style_samples_owner_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY studio_writing_style_samples_owner_all ON public.studio_writing_style_samples USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));


--
-- Name: studio_writing_style_samples studio_writing_style_samples_service; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY studio_writing_style_samples_service ON public.studio_writing_style_samples USING ((auth.role() = 'service_role'::text)) WITH CHECK ((auth.role() = 'service_role'::text));


--
-- Name: studio_writing_styles; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.studio_writing_styles ENABLE ROW LEVEL SECURITY;

--
-- Name: studio_writing_styles studio_writing_styles_owner_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY studio_writing_styles_owner_all ON public.studio_writing_styles USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));


--
-- Name: studio_writing_styles studio_writing_styles_service; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY studio_writing_styles_service ON public.studio_writing_styles USING ((auth.role() = 'service_role'::text)) WITH CHECK ((auth.role() = 'service_role'::text));


--
-- Name: tool_results; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.tool_results ENABLE ROW LEVEL SECURITY;

--
-- Name: tool_results tool_results_service_role_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tool_results_service_role_all ON public.tool_results TO service_role USING (true) WITH CHECK (true);


--
-- Name: tool_results tool_results_user_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tool_results_user_all ON public.tool_results TO authenticated USING ((user_id = auth.uid())) WITH CHECK ((user_id = auth.uid()));


--
-- Name: usage_events; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.usage_events ENABLE ROW LEVEL SECURITY;

--
-- Name: user_feedback; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.user_feedback ENABLE ROW LEVEL SECURITY;

--
-- Name: user_profiles; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;

--
-- Name: user_progress; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.user_progress ENABLE ROW LEVEL SECURITY;

--
-- Name: user_skill_audit; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.user_skill_audit ENABLE ROW LEVEL SECURITY;

--
-- Name: user_skill_audit user_skill_audit_select_self_or_admin; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY user_skill_audit_select_self_or_admin ON public.user_skill_audit FOR SELECT TO authenticated USING (((actor_id = auth.uid()) OR (EXISTS ( SELECT 1
   FROM public.user_profiles
  WHERE ((user_profiles.id = auth.uid()) AND (user_profiles.is_admin = true))))));


--
-- Name: user_skills; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.user_skills ENABLE ROW LEVEL SECURITY;

--
-- Name: user_skills user_skills_select_authenticated; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY user_skills_select_authenticated ON public.user_skills FOR SELECT TO authenticated USING (true);


--
-- Name: user_yang_settings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.user_yang_settings ENABLE ROW LEVEL SECURITY;

--
-- Name: workspace_files; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.workspace_files ENABLE ROW LEVEL SECURITY;

--
-- Name: yang_checkpoints; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.yang_checkpoints ENABLE ROW LEVEL SECURITY;

--
-- Name: user_yang_settings yang_settings_owner; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY yang_settings_owner ON public.user_yang_settings TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));


--
-- Name: user_yang_settings yang_settings_service_role; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY yang_settings_service_role ON public.user_yang_settings TO service_role USING (true) WITH CHECK (true);


--
-- PostgreSQL database dump complete
--

\unrestrict XSX3LOX4kX6orljnHHPsN4aryCbatg347kcYzeFJQ321sBQelCBdvf9BPqZ9Ymk

