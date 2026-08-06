# DuckDuckGo search: Redis Streams consumer groups partition failure XACK XCLAIM

## 1. Streams Consumer Group Patterns - Redis Patterns
<https://redis.antirez.com/fundamental/streams-consumer-patterns.html>

def consume(): # Phase 1: Process any previously assigned but unacked messages while True: messages = redis.xreadgroup('mygroup', 'worker-1', {'mystream': '0'}, # Read PEL history count=100) if not messages or not messages[0][1]: break # PEL is empty process_and_ack(messages) # Phase 2: Read new messages while True: messages = redis.xreadgroup('mygroup', 'worker-1', {'mystream': '>'}, # New messages only block=5000, count=100) process_and_ack(messages) Using ID 0 queries the PEL for messages already assigned to this consumer. Only after clearing the backlog do you switch to >. When a consumer dies permanently, its messages remain orphaned. Other consumers must claim them. ... XPENDING mystream mygroup # Find stale messages XCLAIM mystream mygroup worker-2 60000 # Claim one by one

## 2. Redis Streams | Docs
<https://redis.io/docs/latest/develop/data-types/streams/>

A Redis stream is a data structure that acts like an append-only log but also implements several operations to overcome some of the limits of a typical append-only log. These include random access in O (1) time and complex consumption strategies, such as consumer groups. You can use streams to record and simultaneously syndicate events in real time. Examples of Redis stream use cases include:

## 3. XCLAIM | Docs
<https://redis.io/docs/latest/commands/xclaim/>

3 weeks ago - As a side effect a pending message entry is created in the Pending Entries List (PEL) of the consumer group: it means the message was delivered to a given consumer, but it was not yet acknowledged via XACK. Then suddenly that consumer fails forever. Other consumers may inspect the list of pending messages, that are stale for quite some time, using the XPENDING command. In order to continue processing such messages, they use XCLAIM to acquire the ownership of the message and continue. Consumers can also use the XAUTOCLAIM command to automatically scan and claim stale pending messages. This dynamic is clearly explained in the Stream intro documentation.

## 4. How to Implement Redis Streams Consumer Groups
<https://oneuptime.com/blog/post/2026-01-30-redis-streams-consumer-groups/view>

January 30, 2026 - Other consumers can claim these messages using XCLAIM or XAUTOCLAIM. // message-recovery.js // Recovering messages from failed consumers const Redis = require('ioredis'); const { arrayToObject } = require('./consumer-group-setup'); class ...

## 5. Redis Streams — XADD, Consumer Groups, XCLAIM, MAXLEN
<https://systeminternals.dev/redis/streams/>

Append-only event streams in Redis: XADD, XREAD, consumer groups with explicit acks, XCLAIM and XAUTOCLAIM for ownership transfer, MAXLEN/MINID retention, vs Kafka.

## 6. Redis Streams and Consumer Groups | redis/redis-doc | DeepWiki
<https://deepwiki.com/redis/redis-doc/4.1-redis-streams-and-consumer-groups>

This document covers the Redis Streams data structure and its associated consumer group functionality for distributed message processing. Redis Streams provide an append-only log data structure with support for multiple producers and consumers, message acknowledgment, and fault-tolerant distributed consumption patterns.

## 7. handbook-infra/message-brokers/redis-streams/consumer-groups ... - GitHub
<https://github.com/vzahanych/handbook-infra/blob/main/message-brokers/redis-streams/consumer-groups.md>

Delivered-but-unacknowledged entries are tracked in a pending entries list, and a consumer confirms completion with XACK; if a consumer dies, another can claim its stale pending entries with XCLAIM (or XAUTOCLAIM), giving at-least-once delivery and recovery. This is the feature that makes Streams a real alternative to a dedicated broker for many workloads.

## 8. How to use consumer groups in Redis Streams | InfoWorld
<https://www.infoworld.com/article/2257824/how-to-use-consumer-groups-in-redis-streams.html>

November 21, 2018 - The result of these commands is illustrated in Figure 8. XCLAIM also comes in handy when one of your consumer processors is slow, resulting in a backlog of unprocessed data. ... Figure 8. Alice claimed all of the data from Bob. In the previous article, we covered the basics of how to use Redis Streams. We went a bit deeper in this article and explained when to use consumer groups and how they work. Consumer groups in Redis Streams reduce your burden when it comes to managing data partitions, their lifecycles, and data safety.

## 9. Redis™ Streams vs Apache Kafka® - Instaclustr
<https://www.instaclustr.com/blog/redis-streams-vs-apache-kafka/>

March 28, 2025 - There are a couple of commands ... per entry. Used in conjunction with the XCLAIM command, this allows you to reassign messages from one consumer to another....

## 10. Single-shot reliable consumers with XREADGROUP CLAIM in Redis 8.4 | Redis
<https://redis.io/blog/single-shot-reliable-consumers-with-xreadgroup-claim-in-redis-84/>

May 26, 2026 - The pending entry sits in the PEL until the client confirms it has finished processing the message by calling XACK. Once acknowledged, the entry is removed and Redis considers that message done. This is what makes Streams suitable for work queues and event pipelines: if a consumer crashes mid-processing — or simply takes too long — its pending entries stay in the PEL. Another consumer in the same group can then take ownership of those entries with XCLAIM and pick up the work.

## 11. Redis Streams for Real-Time Pipelines: Consumer Groups, XADD/XREAD, Persistence | PipeCode Blog | PipeCode
<https://pipecode.ai/blogs/redis-streams-real-time-consumer-groups-xadd-xread>

1 month ago - Poll XPENDING for entries idle > 30 seconds; use XCLAIM to reassign them to a DLQ worker; the worker XADDs to a secondary stream events:dlq with the failure metadata and XACKs the original. This is the standard poison-pill pattern. Each box has one command family + one config line — that is what makes Streams operationally cheap. Kafka's equivalent whiteboard would need Producer + Consumer + Broker + Controller + Topic + Partition + Retention + Compaction lines.

## 12. Redis streaming | Docs
<https://redis.io/docs/latest/develop/use-cases/streaming/>

Recover unacknowledged entries from crashed consumers, so a worker dying mid-message does not silently lose work (entries trimmed by MAXLEN ~ before they are acked are surfaced in XAUTOCLAIM's deleted-IDs list, so the caller can route them to a dead-letter store rather than retry against a missing payload). Partition streams by tenant, region, or entity for load distribution and per-entity event sourcing.

## 13. How to Use XCLAIM in Redis Streams to Claim Pending Messages
<https://oneuptime.com/blog/post/2026-03-31-redis-how-to-use-xclaim-in-redis-streams-to-claim-pending-messages/view>

March 31, 2026 - XCLAIM transfers ownership of specific pending messages from one consumer to another in a Redis Stream consumer group, enabling recovery from consumer failures. It requires a minimum idle time to prevent race conditions between active consumers.

## 14. How to Use XCLAIM in Redis Streams to Reassign Pending Messages
<https://oneuptime.com/blog/post/2026-03-31-redis-xclaim-reassign-pending/view>

March 31, 2026 - XCLAIM is the manual mechanism for recovering stalled messages in Redis Streams consumer groups. By checking idle time and delivery counts via XPENDING, you can implement robust failure detection and automatic recovery.

## 15. XACK | Docs
<https://redis.io/docs/latest/commands/xack/>

1 week ago - The XACK command removes one or multiple messages from the Pending Entries List (PEL) of a stream consumer group. A message is pending, and as such stored inside the PEL, when it was delivered to some consumer, normally as a side effect of calling XREADGROUP, or when a consumer took ownership ...

## 16. How to Handle Consumer Failures in Redis Streams
<https://oneuptime.com/blog/post/2026-03-31-redis-handle-consumer-failures-streams/view>

March 31, 2026 - def start_consumer(consumer_name): ... {e}") Handle consumer failures in Redis Streams by running XAUTOCLAIM on startup to reclaim messages idle beyond your processing timeout....

## 17. Redis Stream Message Claiming
<https://faststream.ag2.ai/latest/redis/streams/claiming/>

When working with Redis Stream ... failed to process them. FastStream provides a mechanism to automatically claim these pending messages using Redis's XAUTOCLAIM command through the min_idle_time ......

## 18. RubyDoc.info: Module: Redis::Commands::Streams – Documentation for redis/redis-rb (master) – RubyDoc.info
<https://www.rubydoc.info/github/redis/redis-rb/Redis/Commands/Streams>

redis.xack('mystream', 'mygroup', '1526569495631-0') ... Add new entry to the stream. ... redis.xadd('mystream', { f1: 'v1', f2: 'v2' }, id: '0-0', maxlen: 1000, approximate: true, nomkstream: true) ... Transfers ownership of pending stream entries that match the specified criteria. redis.xautoclaim('mystream', 'mygroup', 'consumer1', 3600000, '0-0') redis.xclaim('mystream', 'mygroup', 'consumer1', 3600000, '0-0', count: 50)

## 19. RedisStreamCommands (Spring Data Redis 4.0.5 API)
<https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/connection/RedisStreamCommands.html>

Change the ownership of a pending message to the given new consumer. ... (byte @NonNull [] key, @NonNull String group, @NonNull String newOwner, @NonNull RedisStreamCommands.XClaimOptions options)

## 20. Streams and Consumer Groups | redis/redis | DeepWiki
<https://deepwiki.com/redis/redis/3.2-streams-and-consumer-groups>

Streams and Consumer Groups Relevant source files Purpose and Scope This document explains the Redis Streams data type implementation, focusing on its radix tree storage architecture, consumer groups, pending entry lists (PEL), blocking operations, and idempotency features.

## 21. blog/posts/2026-03-31-redis-xack-consumer-groups/README.md at ... - GitHub
<https://github.com/OneUptime/blog/blob/master/posts/2026-03-31-redis-xack-consumer-groups/README.md>

Tags: Redis, XACK, Stream, Consumer Group, Acknowledgment Description: Learn how to use XACK in Redis Streams to acknowledge message processing within consumer groups, remove messages from the pending list, and build reliable at-least-once message processing.

## 22. Module F-9: Streams: Append-Only Logs and Consumer Groups — Redis In ...
<https://academy.jatinjainsaraf.com/redis-in-depth/streams-consumer-groups>

XADD/XREAD/XRANGE, the XREADGROUP consumer group model, XACK and the Pending Entry List, XAUTOCLAIM for crash recovery, dead-letter handling, and when Redis Streams beats Kafka or BullMQ.

## 23. Redis Streams: A Log With Consumer Groups - Intraview Explore
<https://www.intraview.ai/explore/redis/redis/tours/streams/>

XCLAIM is how a consumer group recovers from a dead consumer. When consumer A crashes mid-processing, its PEL entries sit unacknowledged indefinitely. Another consumer calls XCLAIM with a min-idle-time threshold, and Redis transfers ownership for each claimed entry

## 24. Using Redis Streams with NestJS: Part 3 - Consumer groups
<https://hackernoon.com/using-redis-streams-with-nestjs-part-3-consumer-groups>

This is part 3 of a 3-part series, where we will explore how to use Redis streams with NestJS.

## 25. Redis Agent Architecture: Production System Design Guide | Markaicode
<https://markaicode.com/architecture/redis-agent-architecture/>

Redis Streams add real operational surface. Consumer group rebalancing, pending-entry cleanup, and dead-letter handling are extra failure modes a simple queue (or no queue at all) doesn't have. You may not need durability at the message layer.

## 26. Implement a Redis event-streaming pipeline in Rust with redis-rs
<https://redis.io/docs/latest/develop/use-cases/streaming/rust/>

Two consumer groups read the same stream: notifications — two consumers ( worker-a , worker-b ) sharing the work, modelling a fan-out worker pool.Once the consumer has processed an entry, XACK tells Redis it can drop the entry from the group's pending list

## 27. Using redis streams to build more resilient services - Speaker Deck
<https://speakerdeck.com/chirimoya/using-redis-streams-to-build-more-resilient-services>

Read data via Consumer Group Redis stream provides the concept. of consumer groups, allowing multiple consumers to process the same stream to implement load balancing.

## 28. How to Use Redis Streams
<https://www.squash.io/how-to-use-redis-streams/>

Consumer groups in Redis Streams provide fault-tolerant message consumption. If a consumer fails or disconnects, the other consumers in the group will take over the processing of the unacknowledged entries.

## 29. Redis Stream — надёжность и масштабируемость ваших... / Хабр
<https://habr.com/ru/articles/456270/>

Redis Stream — новый абстрактный тип данных, представленный в Redis с выходом версии 5.0 Концептуально Redis Stream — это List, в который вы можете добавлять записи. Каждая запись имеет уникальный идентификатор.

## 30. Consumer group forgets "last-delivered-id" after restart when using...
<https://github.com/redis/redis/issues/7105>

One consumer is doing blocking reads with XREADGROUP GROUP client1 client1 COUNT 1 BLOCK 0 STREAMS samples >, and XACK samples client1 $id after processing. I stop my producer and consumer in that order (all samples processed). redis-clisays

## 31. XADD & XREAD — Redis Streams — Build Redis from Scratch
<https://shipthatcode.com/courses/build-redis/lessons/streams>

Where this leads. This exercise stops short of consumer groups — the feature that lets multiple workers cooperatively split a stream's workload with acknowledgment and at-least-once delivery (Redis's answer to Kafka's consumer groups / SQS's visibility timeout).

## 32. Message Queues Compared: RabbitMQ vs Kafka vs Redis Streams
<https://harborsoftware.com/2024/09/13/message-queues-compared-rabbitmq-kafka-redis-streams/>

Multiple consumer groups: Multiple independent consumer groups can read the same topic at their own pace. One group for real-time processing, another for analytics, another for audit logging, another for search indexing. Each tracks its own offset.

## 33. Redis as an Auth Buffer: Implementing Write-Behind Caching for Logins
<https://mojoauth.com/blog/redis-auth-buffer-write-behind-caching-logins>

Redis Streams with consumer groups give an at-least-once, replayable buffer, safer for auth writes than fire-and-forget INCR/SET that vanish on a crash.

## 34. Building Scalable Applications Using Redis as... - Semaphore
<https://semaphore.io/blog/redis-message-broker>

Redis Streams. First-class stream processing capabilities, flexible stream traversal along with advanced features such as consumer groups, auto-claiming and observability.

## 35. Redis Streams
<https://devopedia.org/redis-streams>

XACK, XCLAIM and XPENDING are other commands associated with consumer groups. Information: XINFO shows details of streams and consumer groups. XLEN gives number of entries in a stream. What are main features of Redis Streams?

## 36. Using Redis Streams in C# without losing your mind - Toxigon
<https://toxigon.com/implementing-redis-streams-in-c-sharp>

Consumer groups in Redis Streams are one of those things that sound amazing in theory, until you actually try to use them.The StackExchange.Redis library has the methods you'd expect: XReadGroup, XAck, XClaim, etc. But the documentation is... sparse.

## 37. Redis streaming with node-redis | Docs
<https://redis.io/docs/latest/develop/use-cases/streaming/nodejs/>

After processing each entry, the consumer calls XACK so Redis can drop it from the group's pending list. ... Multiple consumer groups, one stream. The big ...

## 38. Redis Streams Decoded: 15 Questions That Changed How I Think ...
<https://medium.com/@pur4v/redis-streams-decoded-15-questions-that-changed-how-i-think-about-message-queues-24bd0dbe3189>

5 Dec 2025 ... With Streams + Consumer Groups + Auto-claim, you get at-least-once delivery (message might be processed twice if worker crashes mid ...

## 39. Introduction to Redis Streams
<https://redis-doc-test.readthedocs.io/en/latest/topics/streams-intro/>

XGROUP is used in order to create, destroy and manage consumer groups. XREADGROUP is used to read from a stream via a consumer group. XACK is the command that ...

## 40. How to Use Redis Streams for Event Processing - OneUptime
<https://oneuptime.com/blog/post/2026-02-20-redis-streams-event-processing/view>

20 Feb 2026 ... ... consumer groups, and handle failures. How Redis Streams Work. A stream is an append-only log of entries. Each entry has a unique ID ...

## 41. How Does Redis Streams Work and When Should We Use it?
<https://www.nootcode.com/knowledge/en/redis-streams>

Consumer Groups Mechanism. Similar to Kafka consumer groups, Redis Streams supports consumer group semantics: ... Partitioning: Advanced partition management is ...

## 42. Redis streaming with redis-py | Docs
<https://redis.io/docs/latest/develop/use-cases/streaming/redis-py/>

After processing each entry, the consumer calls XACK so Redis can drop it from the group's pending list. ... Multiple consumer groups, one stream. The big ...

## 43. How to remove redis stream pending entries from a consumer? - Stack Overflow
<https://stackoverflow.com/questions/74621959/how-to-remove-redis-stream-pending-entries-from-a-consumer>

## 44. XREADGROUP | Docs
<https://redis.io/docs/latest/commands/xreadgroup/>

3 weeks ago - In order to implement such semantics, consumer groups require explicit acknowledgment of the messages successfully processed by the consumer, via the XACK command. This is needed because the stream will track, for each consumer group, who is processing what message.

## 45. XPENDING | Docs
<https://redis.io/docs/latest/commands/xpending/>

2 days ago - The XPENDING command is the interface to inspect the list of pending messages, and is as thus a very important command in order to observe and understand what is happening with a streams consumer groups: what clients are active, what messages are pending to be consumed, or to see if there are idle messages. Moreover this command, together with XCLAIM is used in order to implement recovering of consumers that are failing for a long time, and as a result certain messages are not processed: a different consumer can claim the message and continue.

## 46. XAUTOCLAIM | Docs
<https://redis.io/docs/latest/commands/xautoclaim/>

3 weeks ago - xautoclaim_options( key: K, group: G, consumer: C, min_idle_time: MIT, start: S, options: streams ) → (streams::StreamAutoClaimReply) ... O(1) if COUNT is small. ... This command transfers ownership of pending stream entries that match the specified criteria. Conceptually, XAUTOCLAIM is equivalent to calling XPENDING and then XCLAIM, but provides a more straightforward way to deal with message delivery failures via SCAN-like semantics.

## 47. (untitled)
</clev?event=StartpageResultClick&sc=2sbbv9Ind9Fp9Ju2XDmlv61tSjdiexikx02kxsiITMC83MUyuLnuIcJIaniYRs6BHzyEKoDyM629kv67KBQFCLCh2Wzu9sq9&payload={"bdsSessionId":"ad98fddfdc334ab2951630af187d7db9","cheqId":"","countryCode":"IL","deviceType":"desktop","endpoint":"search.serp","hasGoogleAds":true,"page_id":"K2LSMpZ6qScMZIDy","queryCategory":"web","segment":"startpage.opera","session_id":"1aR1736LecmnTYo9w","surface":"serp-web","transport":"href-request"}>
