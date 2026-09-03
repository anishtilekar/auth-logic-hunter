package dev.authhunter.seeded;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/coupons")
public class CouponController {

    private final CouponStore store;

    public CouponController(CouponStore store) {
        this.store = store;
    }

    public record CreateRequest(Integer discountPercent) {}

    @PostMapping
    public ResponseEntity<Map<String, Object>> create(
            @RequestHeader("X-User") String user,
            @RequestBody(required = false) CreateRequest body) {
        int pct = body != null && body.discountPercent() != null ? body.discountPercent() : 10;
        CouponStore.Coupon c = store.create(user, pct);
        return ResponseEntity.status(HttpStatus.CREATED).body(view(c));
    }

    @GetMapping("/{code}")
    public ResponseEntity<Map<String, Object>> get(
            @RequestHeader("X-User") String user, @PathVariable String code) {
        CouponStore.Coupon c = store.get(code);
        if (c == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(view(c));
    }

    /**
     * PLANTED BUG (double-redeem race). The "already redeemed?" check and the
     * "mark redeemed" write are separate, unsynchronized steps. Two concurrent
     * requests can both pass the check before either writes, so both succeed
     * and redemptionCount reaches 2 for a coupon that must be used once.
     * The sleep widens the window so the race is reliably reproducible; the
     * bug exists without it.
     */
    @PostMapping("/{code}/redeem")
    public ResponseEntity<Map<String, Object>> redeem(
            @RequestHeader("X-User") String user, @PathVariable String code)
            throws InterruptedException {
        CouponStore.Coupon c = store.get(code);
        if (c == null) {
            return ResponseEntity.notFound().build();
        }
        if (c.redeemed) {
            return ResponseEntity.status(HttpStatus.CONFLICT)
                    .body(Map.of("error", "already redeemed", "code", code));
        }
        Thread.sleep(50);
        c.redeemed = true;
        c.redeemedBy = user;
        c.redemptionCount.incrementAndGet();
        return ResponseEntity.ok(view(c));
    }

    private static Map<String, Object> view(CouponStore.Coupon c) {
        return Map.of(
                "code", c.code,
                "createdBy", c.createdBy,
                "discountPercent", c.discountPercent,
                "redeemed", c.redeemed,
                "redeemedBy", c.redeemedBy == null ? "" : c.redeemedBy,
                "redemptionCount", c.redemptionCount.get());
    }
}
