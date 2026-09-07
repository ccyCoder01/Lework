package cache

import (
	"fmt"
	"testing"
	"time"
)

type testBiz struct {
	ProjectID   uint
	SessionID   uint
	AssistantID uint
	Uin         uint
}

func TestCache_PutAndGet(t *testing.T) {
	c := New[testBiz](time.Hour)
	c.Put("key", testBiz{ProjectID: 1, SessionID: 2, AssistantID: 3, Uin: 4})

	got := c.Get("key")
	if got == nil {
		t.Fatal("expected non-nil result")
	}
	if got.ProjectID != 1 || got.SessionID != 2 || got.AssistantID != 3 || got.Uin != 4 {
		t.Errorf("got %+v, want ProjectID=1 SessionID=2 AssistantID=3 Uin=4", got)
	}
}

func TestCache_Expired(t *testing.T) {
	c := New[testBiz](time.Nanosecond)
	c.Put("key", testBiz{ProjectID: 1})

	time.Sleep(time.Millisecond)

	got := c.Get("key")
	if got != nil {
		t.Errorf("expected nil for expired entry, got %+v", got)
	}

	c.mu.RLock()
	_, ok := c.entries["key"]
	c.mu.RUnlock()
	if ok {
		t.Error("expired entry should be removed from map after get")
	}
}

func TestCache_Remove(t *testing.T) {
	c := New[testBiz](time.Hour)
	c.Put("key", testBiz{ProjectID: 1})

	c.Remove("key")

	if got := c.Get("key"); got != nil {
		t.Errorf("expected nil after remove, got %+v", got)
	}
}

func TestCache_NotFound(t *testing.T) {
	c := New[testBiz](time.Hour)
	if got := c.Get("nonexistent"); got != nil {
		t.Errorf("expected nil for nonexistent key, got %+v", got)
	}
}

func TestCache_PutOverwrite(t *testing.T) {
	c := New[testBiz](time.Hour)
	c.Put("key", testBiz{ProjectID: 1})
	c.Put("key", testBiz{ProjectID: 2})

	got := c.Get("key")
	if got == nil || got.ProjectID != 2 {
		t.Errorf("expected ProjectID=2 after overwrite, got %+v", got)
	}
}

func TestCache_ConcurrentAccess(t *testing.T) {
	c := New[testBiz](time.Hour)
	done := make(chan struct{})
	for i := 0; i < 10; i++ {
		go func(i int) {
			for j := 0; j < 100; j++ {
				key := fmt.Sprintf("model:run-%d", i)
				c.Put(key, testBiz{ProjectID: uint(i)})
				c.Get(key)
				c.Remove(key)
			}
			done <- struct{}{}
		}(i)
	}
	for i := 0; i < 10; i++ {
		<-done
	}
}
