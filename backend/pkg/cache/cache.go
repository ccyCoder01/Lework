package cache

import (
	"sync"
	"time"
)

// Cache is a generic key‑value store where each entry expires after a fixed TTL.
// Key is always string; value is any comparable type V.
//
// Expired entries are lazily removed when Get is called. Use Remove for
// proactive deletion. Safe for concurrent use.
type Cache[V any] struct {
	entries map[string]entry[V]
	mu      sync.RWMutex
	ttl     time.Duration
}

type entry[V any] struct {
	value   V
	expires time.Time
}

// New creates a Cache with the given TTL.
func New[V any](ttl time.Duration) *Cache[V] {
	return &Cache[V]{
		entries: make(map[string]entry[V]),
		ttl:     ttl,
	}
}

// Put inserts or overwrites the value for key, resetting the expiration timer.
func (c *Cache[V]) Put(key string, value V) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.entries[key] = entry[V]{
		value:   value,
		expires: time.Now().Add(c.ttl),
	}
}

// Get returns a copy of the value for key, or nil if not found or expired.
func (c *Cache[V]) Get(key string) *V {
	c.mu.RLock()
	e, ok := c.entries[key]
	c.mu.RUnlock()
	if !ok {
		return nil
	}
	if time.Now().After(e.expires) {
		c.mu.Lock()
		delete(c.entries, key)
		c.mu.Unlock()
		return nil
	}
	cp := e.value
	return &cp
}

// Remove deletes the entry for key. No‑op if key does not exist.
func (c *Cache[V]) Remove(key string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	delete(c.entries, key)
}
