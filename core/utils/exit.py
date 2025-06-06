
def end_with_msg(event_logger, exception: Exception, msg: str) -> None:
        # Single point of exit in the entire application
        if exception is not None:
            event_logger.warning(msg)
            raise exception(msg)
        else:
            event_logger.info(msg)
            exit(1)