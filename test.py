from timeframe import TimeFrame


def test() -> None:
    import random
    import time

    with TimeFrame(name='Text request') as time_frame:
        with time_frame.create(name='Prompt') as group_prompt:
            with group_prompt.create(name='Prompt request', retries=5, ignore_retries=(TimeoutError,)) as event_frame:
                function_call = False
                for frame in event_frame:
                    with frame:
                        time.sleep(random.uniform(0, 0.4))  # Stimulate doing network operation
                        if random.random() < 0.2:
                            raise ValueError  # Stimulate a complete random chance of a network error occur
                        if random.random() < 0.3:
                            raise TimeoutError
                        if random.random() < 0.9:
                            function_call = True
            if function_call:
                with group_prompt.create(name='Function call `mul`', retries=0):
                    time.sleep(random.uniform(0, 0.01))  # Stimulate doing network operation
                with group_prompt.create(name='Function Response', retries=5) as event_frame:
                    for frame in event_frame:
                        with frame:
                            time.sleep(random.uniform(0, 0.4))  # Stimulate doing network operation
                            if random.random() < 0.7:
                                raise ValueError  # Stimulate a complete random chance of a network error occur
    print(time_frame.traceback_format())
    print('---Display on discord---')
    print(time_frame.frame_format_dc())
    print('---Display on mono---')
    print(time_frame.frame_format_mono())
    print('---Display on markdown---')
    print(time_frame.frame_format_custom())


if __name__ == '__main__':
    test()
