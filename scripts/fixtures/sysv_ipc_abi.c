/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE
#include <sys/msg.h>
#include <sys/sem.h>
#include <sys/shm.h>
#ifdef IPC_KERNEL_UAPI_TEST
#include <asm/msgbuf.h>
#include <asm/sembuf.h>
#include <asm/shmbuf.h>
#define SAME(user, field, kernel, member) _Static_assert(__builtin_offsetof(struct user, field) == __builtin_offsetof(struct kernel, member), "actual kernel UAPI: " #field)
_Static_assert(sizeof(struct ipc_perm) == sizeof(struct ipc64_perm), "IPC permission wire size");
SAME(msqid_ds, msg_cbytes, msqid64_ds, msg_cbytes);
SAME(msqid_ds, msg_qbytes, msqid64_ds, msg_qbytes);
SAME(semid_ds, sem_nsems, semid64_ds, sem_nsems);
SAME(shmid_ds, shm_segsz, shmid64_ds, shm_segsz);
SAME(shmid_ds, shm_cpid, shmid64_ds, shm_cpid);
SAME(shmid_ds, shm_nattch, shmid64_ds, shm_nattch);
#if __SIZEOF_LONG__ == 4
SAME(msqid_ds, __msg_stime_lo, msqid64_ds, msg_stime);
SAME(semid_ds, __sem_otime_lo, semid64_ds, sem_otime);
SAME(shmid_ds, __shm_atime_lo, shmid64_ds, shm_atime);
#else
SAME(msqid_ds, msg_stime, msqid64_ds, msg_stime);
SAME(semid_ds, sem_otime, semid64_ds, sem_otime);
SAME(shmid_ds, shm_atime, shmid64_ds, shm_atime);
#endif
#endif
#define OFFSET(type, field, value) _Static_assert(__builtin_offsetof(struct type, field) == value, "kernel wire offset: " #field)
#if __SIZEOF_LONG__ == 4
_Static_assert(IPC_STAT == 0x102 && sizeof(struct ipc_perm) == 36, "time64 IPC convention");
OFFSET(msqid_ds, msg_cbytes, 60);
OFFSET(msqid_ds, msg_qnum, 64);
OFFSET(msqid_ds, msg_stime, 88);
OFFSET(semid_ds, sem_nsems, 52);
OFFSET(semid_ds, sem_otime, 64);
OFFSET(shmid_ds, shm_cpid, 64);
OFFSET(shmid_ds, shm_nattch, 72);
OFFSET(shmid_ds, shm_atime, 88);
#else
_Static_assert(IPC_STAT == 2 && sizeof(struct ipc_perm) == 48, "native LP64 convention");
OFFSET(msqid_ds, msg_cbytes, 72);
OFFSET(msqid_ds, msg_stime, 48);
OFFSET(semid_ds, sem_nsems, 64);
OFFSET(semid_ds, sem_otime, 48);
OFFSET(shmid_ds, shm_atime, 56);
#endif
union test_semun { int val; struct semid_ds *buf; unsigned short *array; };
long __syscall_ret(unsigned long result) { return result; }
int run(void)
{
	struct msqid_ds msg;
	struct semid_ds sem;
	struct shmid_ds shm;
	if (msgctl(40, IPC_STAT, &msg) || msg.msg_cbytes != 7 || msg.msg_qnum != 1 || msg.msg_qbytes != 8192 ||
	    msg.msg_lspid != 43 || msg.msg_lrpid != 44 || msg.msg_stime != 0x189abcdefLL ||
	    msg.msg_rtime != 0x200000009LL || msg.msg_ctime != 0x30000000aLL) return 1;
	if (semctl(41, 0, IPC_STAT, (union test_semun){.buf = &sem}) || sem.sem_nsems != 2 ||
	    sem.sem_otime != 0x400000011LL || sem.sem_ctime != 0x500000012LL) return 2;
	if (shmctl(42, IPC_STAT, &shm) || shm.shm_segsz != 65536 || shm.shm_cpid != 45 || shm.shm_lpid != 46 ||
	    shm.shm_nattch != 3 || shm.shm_atime != 0x600000015LL || shm.shm_dtime != 0x700000016LL ||
	    shm.shm_ctime != 0x800000017LL) return 3;
	return 0;
}
