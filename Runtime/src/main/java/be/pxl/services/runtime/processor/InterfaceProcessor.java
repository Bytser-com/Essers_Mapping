package be.pxl.services.runtime.processor;

import be.pxl.services.runtime.domain.ClaimedInterface;

/**
 * Extension point invoked for every claimed customer XML interface.
 * Downstream stories (package retrieval, XML mapping conversion, and delivery)
 * plug directly into this contract.
 */
@FunctionalInterface
public interface InterfaceProcessor {

    void process(ClaimedInterface claimedInterface, byte[] xmlContent);
}
