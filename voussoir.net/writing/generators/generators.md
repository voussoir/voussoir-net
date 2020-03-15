[tag:programming.python] [tag:tutorial]

Generators
==========

## What are they

Generators are a type of iterable that create their contents on the fly. Unlike a list, whose entire contents are available before beginning any loops or manipulations, generators don't know how many items they will produce or when they will stop. They can even go on forever!


## Writing one

Writing a generator looks like writing a function, but instead of `return`, you use `yield`. The object which is yielded is what you'll get when you do a loop over the generator. This one lets you count to a billion:

```Python
def billion():
    x = 0
    while x < 1000000000:
        yield x
        x += 1
```

I purposely used a `while` loop instead of `for x in range()` to show the extra work.

Note that, unlike a `return` statement, you can include more code after a `yield` statement. Also notice that generators keep track of their internal state -- the `billion` generator has an `x` that it increments every time you loop over it. You can imagine the code pausing after the `yield` line, and resuming when you come back for the next cycle. Try this with some extra print statements to help visualize.

Generators can also take arguments. Here's a generator that counts to a custom amount:

```Python
def count_to(y):
    x = 0
    while x < y:
        yield x
        x += 1
```


## Using one

Although generators look like functions when you're writing them, they feel more like classes when using them. Remember that generators don't calculate their contents until they are actually used in a loop, so simply doing:

```Python
numbers = count_to(100)
```

does **not** create a list of 100 numbers. It creates a new instance of the generator that is ready to be iterated over, like this:

```Python
numbers = count_to(100)
for number in numbers:
    print(number)
```

or this:

```Python
for number in count_to(100):
    print(number)
```

This should remind you of:

```Python
for number in range(100):
    print(number)
```

because the `range` class behaves a lot like a generator ([but not exactly](http://stackoverflow.com/a/13092317)).


Generators are excellent for cases where using a list is infeasible or unnecessary. In order to loop over a list, you have to generate the entire thing first. If you're only going to use each item once, storing the entire list can be a big memory waste when a generator could take its place. With a generator, the items are created, used, and thrown away, so memory can be recycled.

Since generators can go on forever, they're great for abstracting out ugly `while` loops, so you can get down to business faster.

To get a single item from a generator without looping, use `next(generator)`.

## StopIteration

Generators pause and resume a lot, but they still flow like normal functions. As long as there is no endless `while` loop inside, they'll come to an end at some point. When a generator is all finished, it will raise a `StopIteration` exception every time you try to do `next()` on it. Luckily, `for` loops will detect this automatically and stop themselves.

```Python
>>> g = count_to(10)
>>> l = list(g)
>>> next(g)
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
StopIteration
```

Earlier, I said that generators use `yield` instead of `return`, but in fact you can include a return statement too. If it is encountered, it will raise a `StopIteration`, and the generator will not resume even if there is more code.

```Python
>>> def generator():
...     yield 1
...     return 2
...     yield 3
...
>>>
>>> g = generator()
>>> next(g)
1
>>> next(g)
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
StopIteration: 2
>>> next(g)
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
StopIteration
>>>
```

Notice that the 2 became part of the StopIteration that was raised at that line.


## Minor notes

- You cannot access the items of a generator by index, because only one item exists at a time. Once you do a loop over a generator, those items are gone forever unless you kept them somewhere else.


## More examples

### Yielding individual items from batches

Suppose you're getting data from an imaginary website which sends you items in groups of 100. You want to let the user loop over the items without having to worry about the groups.

```Python
def item_generator(url):
    page = 0
    while True:
        # get_items is a pretend method that collects the 100 items from that page
        batch = get_items(url, page=page)

        if len(batch) == 0:
            # for this imaginary website, the batch will be empty when that page
            # doesn't have any items on it.
            break

        for item in batch:
            # by yielding individual items, the user can just do a for loop
            # over this generator and get them all one by one.
            yield item

        page += 1

    # When the while loop breaks, we reach the end of the function body,
    # concluding the generator.
```

Now the user can just do this:

```Python
comments = item_generator('http://example.com/user/voussoir/comments')
for comment in comments:
    print(comment.body)
```

## Further reading

[Stack Overflow - What are the main uses for `yield from`?](http://stackoverflow.com/questions/9708902/in-practice-what-are-the-main-uses-for-the-new-yield-from-syntax-in-python-3) -- If you like recursive functions, how about recursive generators?

[Stack Overflow - Python generator `send` function purpose?](http://stackoverflow.com/questions/19302530/python-generator-send-function-purpose) -- This quickly dives out of "quick tips" territory.
