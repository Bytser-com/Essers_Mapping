package be.pxl.services.runtime.config;

import java.time.Clock;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.apache.sshd.sftp.client.SftpClient;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ResourceLoader;
import org.springframework.integration.file.remote.session.CachingSessionFactory;
import org.springframework.integration.file.remote.session.SessionFactory;
import org.springframework.integration.sftp.session.DefaultSftpSessionFactory;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

/**
 * Infrastructure beans for SFTP access to {@code sftp-runtime}, drain-loop scheduling,
 * and bounded parallel interface processing using Java 21 virtual threads.
 */
@Configuration
@EnableConfigurationProperties({ RuntimeSftpProperties.class, RuntimePollerProperties.class })
public class RuntimeSftpConfig {

    public static final String RUNTIME_SFTP_DELEGATE_FACTORY = "runtimeSftpDelegateSessionFactory";
    public static final String RUNTIME_SFTP_SESSION_FACTORY = "runtimeSftpSessionFactory";
    public static final String RUNTIME_SFTP_TEMPLATE = "runtimeSftpTemplate";
    public static final String RUNTIME_POLLER_SCHEDULER = "runtimePollerTaskScheduler";
    public static final String RUNTIME_WORKER_EXECUTOR = "runtimeWorkerExecutor";

    private static final int MIN_SESSION_POOL_SIZE = 4;
    private static final int EXTRA_POLLER_SESSIONS = 2;
    private static final int MAX_SCHEDULER_AWAIT_SECONDS = 5;

    /**
     * Registered as its own Spring bean so Spring invokes {@link DefaultSftpSessionFactory#destroy()}
     * on shutdown and cleanly closes the underlying Apache MINA {@code SshClient} NIO2 thread pool.
     */
    @Bean(name = RUNTIME_SFTP_DELEGATE_FACTORY)
    public DefaultSftpSessionFactory runtimeSftpDelegateSessionFactory(
            RuntimeSftpProperties sftpProperties,
            ResourceLoader resourceLoader
    ) {
        // Dedicated SSH connection per pooled session avoids single-TCP pinning & SSH MaxSessions limits.
        DefaultSftpSessionFactory factory = new DefaultSftpSessionFactory(false);
        factory.setHost(sftpProperties.host());
        factory.setPort(sftpProperties.port());
        factory.setUser(sftpProperties.user());
        factory.setTimeout(sftpProperties.connectTimeoutMs());
        if (!sftpProperties.password().isEmpty()) {
            factory.setPassword(sftpProperties.password());
        }
        if (sftpProperties.privateKey() != null && !sftpProperties.privateKey().isBlank()) {
            factory.setPrivateKey(resourceLoader.getResource(sftpProperties.privateKey()));
            if (sftpProperties.privateKeyPassphrase() != null && !sftpProperties.privateKeyPassphrase().isEmpty()) {
                factory.setPrivateKeyPassphrase(sftpProperties.privateKeyPassphrase());
            }
        }
        if (sftpProperties.knownHosts() != null && !sftpProperties.knownHosts().isBlank()) {
            factory.setKnownHostsResource(resourceLoader.getResource(sftpProperties.knownHosts()));
        }
        factory.setAllowUnknownKeys(sftpProperties.allowUnknownKeys());
        return factory;
    }

    @Bean(name = RUNTIME_SFTP_SESSION_FACTORY)
    public SessionFactory<SftpClient.DirEntry> runtimeSftpSessionFactory(
            @Qualifier(RUNTIME_SFTP_DELEGATE_FACTORY) DefaultSftpSessionFactory delegateFactory,
            RuntimeSftpProperties sftpProperties,
            RuntimePollerProperties pollerProperties
    ) {
        int poolSize = recommendedSessionPoolSize(pollerProperties.workerConcurrency());
        CachingSessionFactory<SftpClient.DirEntry> cachingFactory =
                new CachingSessionFactory<>(delegateFactory, poolSize);
        cachingFactory.setSessionWaitTimeout(sftpProperties.sessionWaitTimeoutMs());
        cachingFactory.setTestSession(true);
        return cachingFactory;
    }

    @Bean(name = RUNTIME_SFTP_TEMPLATE)
    public SftpRemoteFileTemplate runtimeSftpTemplate(
            @Qualifier(RUNTIME_SFTP_SESSION_FACTORY) SessionFactory<SftpClient.DirEntry> sessionFactory
    ) {
        return new SftpRemoteFileTemplate(sessionFactory);
    }

    @Bean(name = RUNTIME_POLLER_SCHEDULER)
    @ConditionalOnProperty(prefix = "runtime.poller", name = "enabled", havingValue = "true", matchIfMissing = true)
    public ThreadPoolTaskScheduler runtimePollerTaskScheduler(RuntimePollerProperties pollerProperties) {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("runtime-poller-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(
                Math.min(MAX_SCHEDULER_AWAIT_SECONDS, pollerProperties.shutdownAwaitSeconds()));
        return scheduler;
    }

    @Bean(name = RUNTIME_WORKER_EXECUTOR, destroyMethod = "shutdown")
    @ConditionalOnProperty(prefix = "runtime.poller", name = "enabled", havingValue = "true", matchIfMissing = true)
    public ExecutorService runtimeWorkerExecutor() {
        return Executors.newThreadPerTaskExecutor(Thread.ofVirtual().name("runtime-worker-", 0).factory());
    }

    @Bean
    public Clock runtimeClock() {
        return Clock.systemUTC();
    }

    static int recommendedSessionPoolSize(int workerConcurrency) {
        return Math.max(MIN_SESSION_POOL_SIZE, workerConcurrency + EXTRA_POLLER_SESSIONS);
    }
}
