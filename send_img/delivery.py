import datetime
import json
import logging
import mimetypes
import os
import random
import time

import requests
from gmssl import func, sm3


ALLOWED_CHANNELS = {"email", "chat"}


def encrypt_ht_string(value: str, salt: str) -> str:
    combined = (value + salt).encode("utf-8")
    return sm3.sm3_hash(func.bytes_to_list(combined))


def create_seqnum() -> str:
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")[:-3]
    suffix = "".join(random.choices("0123456789", k=15))
    return timestamp + suffix


def _format_message(template, filepath: str, channel: str, user_id: str) -> str:
    if template is None:
        return ""

    raw = str(template)
    context = {
        "channel": channel,
        "filename": os.path.basename(filepath),
        "filepath": filepath,
        "user_id": user_id,
    }
    try:
        return raw.format(**context)
    except (IndexError, KeyError, ValueError):
        return raw


def _normalize_receivers(recipient: dict) -> str:
    receivers = recipient.get("receivers", recipient.get("user_id"))
    if isinstance(receivers, (list, tuple, set)):
        values = [str(item).strip() for item in receivers if str(item).strip()]
        return ",".join(values)
    return str(receivers or "").strip()


def _get_auth_body(delivery_cfg: dict, recipient: dict, apply_id: str, seqnum: str) -> str:
    auth_body = str(recipient.get("auth_body", delivery_cfg.get("auth_body", ""))).strip()
    if auth_body:
        return auth_body

    salt = str(recipient.get("salt", delivery_cfg.get("salt", ""))).strip()
    if not salt:
        raise ValueError("Missing auth config: set auth_body or salt")

    return encrypt_ht_string(apply_id + seqnum, salt)


def _guess_content_type(path: str) -> str:
    content_type, _ = mimetypes.guess_type(path)
    return content_type or "application/octet-stream"


def _get_upload_type(channel: str) -> str:
    if channel == "chat":
        return "ims_image"
    if channel == "email":
        return "email_file"
    raise ValueError(f"Unknown channel: {channel}")


def send_file(
    url,
    channel,
    applyid,
    seqnum,
    sender,
    receivers,
    authbody,
    title_var,
    content_var,
    img_path,
    receiversType,
    domain_code="AR1",
    timeout=30,
):
    commonHeader_dict = {
        "seqNum": seqnum,
        "operatorId": sender,
        "domainCode": domain_code,
        "authBody": authbody,
    }

    body_dict = {
        "applyId": applyid,
        "channels": channel,
        "receivers": receivers,
        "sender": sender,
        "uploadType": _get_upload_type(channel),
        "receiversType": receiversType,
        "params": json.dumps({"title": title_var, "content": content_var}, ensure_ascii=False),
        "transmitParams": "",
    }

    data_img = {
        "commonHeader": json.dumps(commonHeader_dict, ensure_ascii=False),
        "body": json.dumps(body_dict, ensure_ascii=False),
    }

    try:
        with open(img_path, "rb") as img_file:
            files = {
                "file": (os.path.basename(img_path), img_file, _guess_content_type(img_path))
            }

            response = requests.post(url, files=files, data=data_img, timeout=timeout)
            logging.info("返回信息: %s", response.text)
    except Exception as exc:
        logging.error("打开文件或请求异常: %s", exc)
        return False

    if response.status_code == 200:
        logging.info("发送成功 %s", img_path)
        return True

    logging.error("发送失败 %s", img_path)
    return False


def send_via_channel(filepath: str, channel: str, recipient: dict, general: dict) -> None:
    delivery_cfg = general.get("delivery", {})
    user_id = str(recipient.get("user_id", "")).strip()
    url = str(delivery_cfg.get("url", "")).strip()
    apply_id = str(recipient.get("apply_id", delivery_cfg.get("apply_id", ""))).strip()
    sender = str(recipient.get("sender", delivery_cfg.get("sender", ""))).strip()
    receivers = _normalize_receivers(recipient)
    receivers_type = str(
        recipient.get("receivers_type", delivery_cfg.get("receivers_type", ""))
    ).strip()
    title_var = _format_message(
        recipient.get("title", delivery_cfg.get("title", "{filename}")),
        filepath,
        channel,
        user_id,
    )
    content_var = _format_message(
        recipient.get("content", delivery_cfg.get("content", "{filename}")),
        filepath,
        channel,
        user_id,
    )
    domain_code = str(delivery_cfg.get("domain_code", "AR1")).strip() or "AR1"
    timeout = float(delivery_cfg.get("timeout", 30))

    missing = []
    if not url:
        missing.append("general.delivery.url")
    if not apply_id:
        missing.append("general.delivery.apply_id")
    if not sender:
        missing.append("general.delivery.sender")
    if not receivers:
        missing.append("recipient.user_id/receivers")
    if not receivers_type:
        missing.append("general.delivery.receivers_type")

    if missing:
        raise ValueError("Missing delivery config: " + ", ".join(missing))

    seqnum = create_seqnum()
    authbody = _get_auth_body(delivery_cfg, recipient, apply_id, seqnum)

    success = send_file(
        url=url,
        channel=channel,
        applyid=apply_id,
        seqnum=seqnum,
        sender=sender,
        receivers=receivers,
        authbody=authbody,
        title_var=title_var,
        content_var=content_var,
        img_path=filepath,
        receiversType=receivers_type,
        domain_code=domain_code,
        timeout=timeout,
    )
    if not success:
        raise RuntimeError("send_file returned False")


def try_send_with_retries(
    filepath: str,
    channel: str,
    recipient: dict,
    general: dict,
    retry_count: int,
    retry_delay: float,
) -> bool:
    user_id = recipient.get("user_id")
    for i in range(1, retry_count + 1):
        try:
            send_via_channel(filepath, channel, recipient, general)
            return True
        except Exception as exc:
            logging.warning(
                f"Attempt {i}/{retry_count} failed ({channel}) "
                f"for {filepath} -> user:{user_id}: {exc}"
            )
            time.sleep(retry_delay)

    logging.error(f"All attempts failed ({channel}) for {filepath} -> user:{user_id}")
    return False
