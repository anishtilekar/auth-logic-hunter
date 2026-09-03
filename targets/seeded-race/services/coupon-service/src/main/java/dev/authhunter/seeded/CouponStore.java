package dev.authhunter.seeded;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

/** In-memory coupon store. Thread-safe map; the race is in the controller's logic, not here. */
@Component
public class CouponStore {

    public static final class Coupon {
        public final String code;
        public final String createdBy;
        public final int discountPercent;
        public volatile boolean redeemed = false;
        public volatile String redeemedBy = null;
        /** How many redeem requests actually succeeded — the observable evidence of a double-redeem. */
        public final AtomicInteger redemptionCount = new AtomicInteger(0);

        Coupon(String code, String createdBy, int discountPercent) {
            this.code = code;
            this.createdBy = createdBy;
            this.discountPercent = discountPercent;
        }
    }

    private final Map<String, Coupon> coupons = new ConcurrentHashMap<>();

    public Coupon create(String createdBy, int discountPercent) {
        String code = UUID.randomUUID().toString().substring(0, 8).toUpperCase();
        Coupon c = new Coupon(code, createdBy, discountPercent);
        coupons.put(code, c);
        return c;
    }

    public Coupon get(String code) {
        return coupons.get(code);
    }
}
