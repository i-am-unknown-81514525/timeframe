# timeframe
Python timeframe tool for time monitoring for each event, error handling, traceback recording...

# How to install
```shell
pip install timeframe_event
```
You can also copy timeframe.py from [GitHub](https://github.com/i-am-unknown-81514525/timeframe/blob/main/timeframe/timeframe.py)
and drop it in your project

This project/file only uses standard libraries so installation of additional dependency is not required

# Example
```python
import random, time
from timeframe import TimeFrame
async def func(timeframe: TimeFrame, *args, **kwargs): # Create rt(realtime) function 
    timeframe.print_mono()
    print(args, kwargs)
    

with TimeFrame('test args', name='Text request', rt=func, test_kwargs='test kwargs') as time_frame:
    with time_frame.create(name='Prompt') as group_prompt:
        with group_prompt.create(name='Prompt request', retries=5, ignore_retries=(TimeoutError,)) as event_frame:
            function_call = False
            for frame in event_frame:
                async with frame:
                    time.sleep(random.uniform(0, 0.4))  # Stimulate doing network operation
                    if random.random() < 0.2:
                        raise ValueError  # Stimulate a complete random chance of a network error occur
                    if random.random() < 0.3:
                        raise TimeoutError # Stimulate a complete internet breakdown
                    if random.random() < 0.9:
                        function_call = True
        if function_call:
            with group_prompt.create(name='Function call `mul`', retries=0):
                time.sleep(random.uniform(0, 0.01))  # Stimulate doing network operation
            with group_prompt.create(name='Function Response', retries=5) as event_frame:
                for frame in event_frame:
                    async with frame:
                        time.sleep(random.uniform(0, 0.4))  # Stimulate doing network operation
                        if random.random() < 0.7:
                            raise ValueError  # Stimulate a complete random chance of a network error occur



```

```
>>> print(time_frame.traceback_format())
[596869.233s] Error raised on Attempt 'Attempt #1' from parent 'Prompt request' at TimeFrame 'Text request':
Traceback (most recent call last):

  File "...\timeframe.py", line 260, in test
    raise ValueError  # Stimulate a complete random chance of a network error occur
    ^^^^^^^^^^^^^^^^

ValueError

[596869.397s] Error raised on Attempt 'Attempt #2' from parent 'Prompt request' at TimeFrame 'Text request':
Traceback (most recent call last):

  File "...\timeframe.py", line 260, in test
    raise ValueError  # Stimulate a complete random chance of a network error occur
    ^^^^^^^^^^^^^^^^

ValueError

[596870.032s] Error raised on Attempt 'Attempt #1' from parent 'Function Response' at TimeFrame 'Text request':
Traceback (most recent call last):

  File "...\timeframe.py", line 271, in test
    raise ValueError  # Stimulate a complete random chance of a network error occur
    ^^^^^^^^^^^^^^^^

ValueError

[596870.171s] Error raised on Attempt 'Attempt #2' from parent 'Function Response' at TimeFrame 'Text request':
Traceback (most recent call last):

  File "...\timeframe.py", line 271, in test
    raise ValueError  # Stimulate a complete random chance of a network error occur
    ^^^^^^^^^^^^^^^^

ValueError
```

```
>>> print(time_frame.frame_format_dc(limit=1024)) #Character limit of discord embed field value
Total: 0001.252s (Total Frames: 11)
✅-Prompt (0001.252s)
> ⚠️-Prompt request (0000.607s)
> - ❌-Attempt #1 (0000.203s)
> - ❌-Attempt #2 (0000.164s)
> - ✅-Attempt #3 (0000.240s)
> ✅-Function call `mul` (0000.005s)
> ⚠️-Function Response (0000.640s)
> - ❌-Attempt #1 (0000.390s)
> - ❌-Attempt #2 (0000.139s)
> - ✅-Attempt #3 (0000.111s)
```
Example: 
![image](https://github.com/i-am-unknown-81514525/timeframe/assets/74453352/4b69b30a-f275-4172-bf28-2af999e5c577)

```
>>> print(time_frame.frame_format_mono()) # Use of export as file or display on console
Total: 0001.252s (Total Frames: 11)
✅-Text request (0001.252s)
  ✅-Prompt (0001.252s)
    ⚠️-Prompt request (0000.607s)
      ❌-Attempt #1 (0000.203s)
      ❌-Attempt #2 (0000.164s)
      ✅-Attempt #3 (0000.240s)
    ✅-Function call `mul` (0000.005s)
    ⚠️-Function Response (0000.640s)
      ❌-Attempt #1 (0000.390s)
      ❌-Attempt #2 (0000.139s)
      ✅-Attempt #3 (0000.111s)
```

```pycon
print(timeframe.frame_format_custom()) # Default with markdown
```
Total: 0000.826s (Total Frames: 11)

✅-Prompt (0000.826s)
-  ⚠️-Prompt request (0000.690s)
> - ❌-Attempt #1 (0000.135s)
> - ❌-Attempt #2 (0000.020s)
> - ❌-Attempt #3 (0000.126s)
> - ❌-Attempt #4 (0000.349s)
> - ✅-Attempt #5 (0000.060s)
-  ✅-Function call `mul` (0000.004s)
-  ✅-Function Response (0000.132s)
