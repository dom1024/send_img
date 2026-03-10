import logging
import time


ALLOWED_CHANNELS = {"email", "chat"}


def send_via_channel(filepath: str, channel: str, user_id: str) -> None:
    """
    统一发送入口。
    你只需要在这里根据 channel + user_id 实现真实发送。
    """
    if channel == "email":
        logging.info(f"[EMAIL] {filepath} -> user:{user_id}")
        # TODO: 调用 SMTP 发送
    elif channel == "chat":
        logging.info(f"[CHAT]  {filepath} -> user:{user_id}")
        # TODO: 调用聊天工具 API 发送
    else:
        raise ValueError(f"Unknown channel: {channel}")


def try_send_with_retries(
    filepath: str,
    channel: str,
    user_id: str,
    retry_count: int,
    retry_delay: float,
) -> bool:
    for i in range(1, retry_count + 1):
        try:
            send_via_channel(filepath, channel, user_id)
            return True
        except Exception as e:
            logging.warning(
                f"Attempt {i}/{retry_count} failed ({channel}) "
                f"for {filepath} -> user:{user_id}: {e}"
            )
            time.sleep(retry_delay)

    logging.error(f"All attempts failed ({channel}) for {filepath} -> user:{user_id}")
    return False
