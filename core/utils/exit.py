import sys

def end_with_msg(event_logger, exception: Exception, msg: str) -> None:
    # Single point of fatal exit
    if exception is not None:
        event_logger.warning(msg)
        raise exception(msg)
    else:
        event_logger.info(msg)
        sys.exit(1)