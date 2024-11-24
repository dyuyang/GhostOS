import json

import streamlit as st
from typing import Iterable, List, NamedTuple
from ghostos.core.messages import Message, Role, MessageType, Caller
from ghostos.framework.messages import CompletionUsagePayload, TaskPayload, PromptPayload
from ghostos.helpers import gettext as _


class MessageGroup(NamedTuple):
    msg_name: str
    msg_role: str
    stage: str
    messages: List[Message]


def render_messages(messages: Iterable[Message], debug: bool, prefix: str = ""):
    groups: List[MessageGroup] = []
    group = MessageGroup("", "", "", [])

    for msg in messages:
        if not msg.is_complete():
            continue
        if msg.name != group.msg_name or msg.role != group.msg_role or msg.stage != group.stage:
            if group.messages:
                groups.append(group)
            group = MessageGroup(msg.name, msg.role, msg.stage, [])
        group.messages.append(msg)

    if group.messages:
        groups.append(group)
    for group in groups:
        render_message_group(group, debug, prefix)


def render_message_group(group: MessageGroup, debug: bool, prefix: str = ""):
    role = group.msg_role
    if role not in {Role.ASSISTANT.value, Role.USER.value} and not debug:
        # hide system messages.
        return
    name = group.msg_name
    stage = group.stage
    caption = f"{role}: {name}" if name else role
    render_role = "user" if role == Role.USER.value else "assistant"
    if stage:
        with st.expander(stage, expanded=False):
            with st.chat_message(render_role):
                st.caption(caption)
                for msg in group.messages:
                    render_message_in_content(msg, debug, prefix)
    else:
        with st.chat_message(render_role):
            st.caption(caption)
            for msg in group.messages:
                render_message_in_content(msg, debug, prefix)


def render_message_payloads(message: Message, debug: bool, prefix: str = ""):
    import streamlit_antd_components as sac
    from ghostos.prototypes.streamlitapp.widgets.dialogs import (
        open_task_info_dialog, open_completion_usage_dialog, open_prompt_info_dialog,
        open_message_dialog,
    )

    if not debug:
        st.empty()
        return
    items = [sac.ButtonsItem(label="Detail")]
    task_payload = TaskPayload.read_payload(message)
    if task_payload:
        items.append(sac.ButtonsItem(label="Task Info"))
    completion_usage = CompletionUsagePayload.read_payload(message)
    if completion_usage:
        items.append(sac.ButtonsItem(label="Completion Usage"))
    prompt_payload = PromptPayload.read_payload(message)
    if prompt_payload:
        items.append(sac.ButtonsItem(label="Prompt Info"))
    if items:
        selected = sac.buttons(
            items,
            index=None,
            key=prefix + ":payloads:" + message.msg_id,
        )
        if selected == "Detail":
            open_message_dialog(message)
        elif selected == "Task Info" and task_payload:
            open_task_info_dialog(task_payload.task_id)
        elif selected == "Completion Usage" and completion_usage:
            open_completion_usage_dialog(completion_usage)
        elif selected == "Prompt Info" and prompt_payload:
            open_prompt_info_dialog(prompt_payload.prompt_id)


def render_message_in_content(message: Message, debug: bool, prefix: str = ""):
    if message.type == MessageType.ERROR:
        st.error(f"Error: {message.content}")
    elif MessageType.is_text(message):
        st.markdown(message.content)
    elif MessageType.FUNCTION_CALL.match(message):
        callers = Caller.from_message(message)
        render_message_caller(callers, debug)
    elif MessageType.FUNCTION_OUTPUT.match(message):
        render_message_caller_output(message, debug)
    # todo: more types
    else:
        st.write(message.model_dump(exclude_defaults=True))
        if message.callers:
            render_message_caller(message.callers, debug)
    render_message_payloads(message, debug, prefix)
    st.empty()


def render_message_caller_output(message: Message, debug: bool):
    with st.expander("Caller Output", expanded=debug):
        st.caption(f"function {message.name} output:")
        st.write(message.content)


def render_message_caller(callers: Iterable[Caller], debug: bool):
    with st.expander("Callers", expanded=debug):
        _render_message_caller(callers)


def _render_message_caller(callers: Iterable[Caller]):
    from ghostos.ghosts.moss_agent import MossAction
    for caller in callers:
        if caller.name == MossAction.Argument.name:
            try:
                data = json.loads(caller.arguments)
                arguments = MossAction.Argument(**data)
            except json.JSONDecodeError:
                arguments = MossAction.Argument(code=caller.arguments)

            st.caption(f"function call: {caller.name}")
            st.code(arguments.code)
        else:
            st.caption(f"function call: {caller.name}")
            st.json(caller.arguments)


def render_message_item(msg: Message, debug: bool):
    if not msg.is_complete():
        return
    if MessageType.ERROR.match(msg):
        with st.chat_message("user"):
            st.caption(_("Error"))
            st.error(msg.get_content())
        return
    if msg.role == Role.ASSISTANT.value:
        render_ai_message(msg, debug)
    elif msg.role == Role.USER.value:
        render_user_message(msg, debug)
    elif msg.role == Role.SYSTEM.value:
        render_sys_message(msg, debug)
    elif msg.role == Role.FUNCTION.value:
        render_func_message(msg, debug)
    else:
        render_other_message(msg, debug)


def render_ai_message(msg: Message, debug: bool):
    content = msg.content
    if not content:
        return
    replacements = {
        "<code>": "\n```python\n",
        "</code>": "\n```\n",
        "<moss>": "\n```python\n",
        "</moss>": "\n```\n",
    }
    for key, value in replacements.items():
        content = content.replace(key, value)

    with st.chat_message("ai"):
        if msg.type:
            st.caption(msg.type)
        if msg.name:
            st.caption(msg.name)
        st.markdown(content, unsafe_allow_html=True)
    if debug:
        render_msg_debug(msg)


def render_msg_debug(msg: Message):
    with st.expander(label=_("debug"), expanded=False):
        st.json(msg.model_dump_json(exclude_defaults=True, indent=2))


def render_user_message(msg: Message, debug: bool):
    content = msg.get_content()
    with st.chat_message("user"):
        if msg.name:
            st.caption(msg.name)
        if msg.type:
            st.caption(msg.type)
        st.markdown(content, unsafe_allow_html=True)


def render_sys_message(msg: Message, debug: bool):
    content = msg.content
    with st.chat_message("user"):
        st.caption("system message")
        st.markdown(content, unsafe_allow_html=True)
    if debug:
        render_msg_debug(msg)


def render_func_message(msg: Message, debug: bool):
    content = msg.content
    with st.expander(_("function"), expanded=False):
        if msg.name:
            st.caption(msg.name)
        st.markdown(content, unsafe_allow_html=True)
    if debug:
        render_msg_debug(msg)


def render_other_message(msg: Message, debug: bool):
    content = msg.content
    with st.expander(_("other"), expanded=False):
        if msg.name:
            st.caption(msg.name)
        st.markdown(content, unsafe_allow_html=True)
    if debug:
        render_msg_debug(msg)
