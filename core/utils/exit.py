
def end_with_msg(event_logger, exception: Exception, msg: str) -> None:
    # Single point of exit in the entire application
    if exception is not None:
        # Log the exception, raise out of work
        event_logger.warning(msg)
        raise exception(msg)
    else:
        # Normal exit
        event_logger.info(msg)
        exit(0)